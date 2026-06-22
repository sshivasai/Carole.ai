"""
# backend/core/agent/react_agent.py

Core ReACT (Reasoning and Acting) loop for Worker and Coordinator agents.

Key features:
1. Thought-Action-Observation loop with streaming.
2. Loads recent conversation history from DB for context continuity.
3. Confidence-based research with web search fallback.
4. Retry/backoff for LLM API errors.
5. Working memory persistence.
"""

import uuid
import json
import re
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm.multi_model_router import llm_router
from core.chat.event_bus import event_bus
from core.memory.models import Message, Agent, Project, User
from core.tools.tool_registry import ToolRegistry
from core.tools.context import CancellationToken, ToolExecutionContext, ToolPermissionContext
from core.memory.lancedb_client import lancedb_client
import core.config
from core.config import (
    STRICT_REASONING_GUIDELINES, COMPACTION_SYSTEM_PROMPT, COMPACTION_USER_PROMPT,
)

logger = logging.getLogger("carole.react_agent")


class ReACTAgent:
    def __init__(
        self, agent_id: str, team_id: str, project_id: str,
        name: str, role: str, model: str, system_prompt: str,
        parent_coordinator_id: Optional[str] = None,
        task_id: Optional[str] = None,
        fallback_model: Optional[str] = None,
        reasoning_effort: str = "none",
    ):
        self.agent_id = agent_id
        self.team_id = team_id
        self.project_id = project_id
        self.name = name
        self.role = role
        self.model = model
        self.fallback_model = fallback_model
        self.reasoning_effort = reasoning_effort
        self.system_prompt = system_prompt
        self.topic = f"team:{self.team_id}"
        self.parent_coordinator_id = parent_coordinator_id
        self.task_id = task_id
        # Tracks the DB id of the current response message (for file snapshotting)
        self.active_message_id: str | None = None
        self._worker_results: List[Dict[str, Any]] = []
        self._notification_queue: asyncio.Queue = asyncio.Queue()
        self._listening = False
        self._log = logger.getChild(self.name)

    async def _load_conversation_history(self, db_session: AsyncSession, limit: int = 20) -> List[Dict[str, str]]:
        """Loads recent team messages from the DB to give the agent conversation context."""
        team_uuid = uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id
        stmt = (
            select(Message)
            .where(Message.team_id == team_uuid)
            .where(
                or_(
                    Message.is_private == False,
                    Message.recipient_id == self.agent_id,
                    Message.sender_id == self.agent_id
                )
            )
            .where(Message.sender_id != "system")
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await db_session.execute(stmt)
        messages = list(reversed(result.scalars().all()))

        history = []
        for msg in messages:
            is_self = msg.sender_id == self.agent_id
            
            content_list = []
            
            if is_self:
                content_list.append({"type": "text", "text": msg.text})
            else:
                sender_label = msg.sender_name or msg.sender_id
                content_list.append({"type": "text", "text": f"[{sender_label}]: {msg.text}"})
                
            if msg.attachments:
                for att in msg.attachments:
                    if att.get("type", "").startswith("image/"):
                        content_list.append({
                            "type": "image",
                            "local_path": att.get("local_path"),
                            "mime_type": att.get("type")
                        })
                        
            final_content = content_list[0]["text"] if len(content_list) == 1 else content_list
                
            history.append({
                "role": "assistant" if is_self else "user",
                "content": final_content
            })
        return history

    async def assemble_system_prompt(self, db_session: AsyncSession, current_task: str) -> str:
        """Assembles system prompt with learnings, tools, team roster, and reasoning guidelines.

        Optimized: fetches Agent roster, Project, User, and Team in a single
        pass using joined selects instead of 3 sequential round-trips.
        """
        capabilities_block = "\n====\nCAPABILITIES & MEMORY\n====\n"

        # Single query: fetch all agents for the team
        team_uuid = uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id
        stmt = select(Agent).where(Agent.team_id == team_uuid)
        roster_result = await db_session.execute(stmt)
        teammates = roster_result.scalars().all()

        roster_block = ""
        has_teammates = any(str(t.id) != self.agent_id for t in teammates)
        if has_teammates:
            roster_block = "TEAM ROSTER:\n"
            for teammate in teammates:
                if str(teammate.id) != self.agent_id:
                    roster_block += f"- {teammate.name} (Role: {teammate.role})\n"
            roster_block += "\n"
        capabilities_block += roster_block

        # Joined query: Project → User in two selects (still avoids a 3rd round-trip
        # by using project_id resolved from the agent's own team record)
        human_context = ""
        project_result = await db_session.execute(
            select(Project, User)
            .join(User, User.id == Project.owner_id)
            .where(Project.id == (uuid.UUID(self.project_id) if isinstance(self.project_id, str) else self.project_id))
        )
        row = project_result.first()
        if row:
            _project, user = row
            first = user.first_name or ""
            last = user.last_name or ""
            full_name = f"{first} {last}".strip() or "Unknown User"
            human_context = f"HUMAN CONTEXT:\nThe human user / project owner is {full_name}.\n\n"
        capabilities_block += human_context

        # 1. Generate search embeddings
        query_vector = await llm_router.generate_embeddings(current_task)

        # 2. Search LanceDB for semantic memory
        past_learnings = await lancedb_client.search_learnings(
            vector=query_vector,
            project_id=self.project_id,
            team_id=self.team_id,
            limit=getattr(core.config, "MEMORY_RETRIEVAL_LIMIT", 3)
        )

        # 3. Format past learnings
        learnings_block = ""
        if past_learnings:
            learnings_block = "LESSONS LEARNED:\n"
            for learning in past_learnings:
                learnings_block += f"- Task context: {learning.get('task_summary')}\n  Lesson: {learning.get('lesson_rule')}\n"
            learnings_block += "\n"
        capabilities_block += learnings_block

        # 4. Tool list
        tools_block = "AVAILABLE TOOLS:\n" + ToolRegistry.to_llm_prompt(team_id=str(self.team_id), agent_id=str(self.agent_id)) + "\n\n"
        capabilities_block += tools_block

        # 4.5 Dynamic Skills
        from core.skills.skill_manager import SkillManager
        active_skills = await SkillManager.get_team_skills(db_session, str(self.team_id), active_only=True)
        skill_addendums = ""
        for skill in active_skills:
            if skill.system_prompt_addendum:
                skill_addendums += f"\n[SKILL: {skill.name}]\n{skill.system_prompt_addendum}\n"
            if skill.tools:
                # Append skill tools to the tools block if not already present
                # Note: Tool descriptions should already be in ToolRegistry, but this makes the agent
                # explicitly aware it has these tools specifically enabled by the skill.
                skill_addendums += f"Skill specific tools allowed: {', '.join(skill.tools)}\n"
            if skill.mcp_servers:
                skill_addendums += f"Skill MCP servers available: {', '.join(skill.mcp_servers)}\n"
                
        if skill_addendums:
            capabilities_block += f"\nACTIVE SKILLS:\n{skill_addendums}\n"

        # 5. Worker reports
        worker_results_block = ""
        if self._worker_results:
            worker_results_block = "WORKER REPORTS:\n"
            for wr in self._worker_results:
                worker_results_block += (
                    f"- Agent: {wr.get('agent', 'unknown')}, Task: {wr.get('task_id', 'unknown')}, "
                    f"Status: {wr.get('status', 'unknown')}\n"
                    f"  Result: {wr.get('result', 'No result')[:500]}\n"
                )
            worker_results_block += "\n"
        capabilities_block += worker_results_block

        # Temporal awareness — agents always know the current date/time
        now = datetime.now(timezone.utc)
        temporal_block = (
            f"CURRENT DATE/TIME: {now.strftime('%A, %B %d, %Y %H:%M UTC')}\n"
            f"(Timezone: UTC — adjust to user's local time if mentioned)\n\n"
        )
        capabilities_block = temporal_block + capabilities_block

        # Scratchpad awareness
        scratchpad_block = (
            "SCRATCHPADS:\n"
            f"- Your personal scratchpad: use read_scratchpad(target='personal') / write_scratchpad(content=..., target='personal')\n"
            f"- Shared team scratchpad: use read_scratchpad(target='team') / write_scratchpad(content=..., target='team')\n"
            "Use your personal pad for notes, partial plans, and cross-session memory. "
            "Write to the team pad to share discoveries, breadcrumbs, or decisions your teammates need to know.\n\n"
        )
        capabilities_block += scratchpad_block

        # Reasoning guidelines
        identity_rule = f"\n\nCRITICAL IDENTITY RULE: You are {self.name} ({self.role}). You MUST speak in the first person ('I', 'me'). NEVER refer to {self.name} in the third person. NEVER pretend to be someone else."
        return f"{self.system_prompt}{identity_rule}\n{capabilities_block}{STRICT_REASONING_GUIDELINES}"

    async def run_loop(self, db_session: AsyncSession, initial_prompt: str, attachments: Optional[List[Dict]] = None, token: Optional["CancellationToken"] = None):
        """Runs the core ReACT loop with conversation history and streaming."""
        
        self._listening = True
        listener_task = asyncio.create_task(self._listen_for_notifications())
        
        try:
            await self._run_loop_inner(db_session, initial_prompt, attachments, token)
        except asyncio.CancelledError:
            # User clicked "Stop Generating" — persist whatever was partially generated
            partial = getattr(self, "_current_thought_buffer", "").strip()
            reasoning = getattr(self, "_current_reasoning_buffer", None) or None
            
            async def _cleanup_cancelled_task():
                # We must use a new session because the task is cancelled,
                # and awaiting on the existing db_session might raise CancelledError.
                from core.memory.database import async_session
                async with async_session() as cleanup_db:
                    stop_note = "\n\n*[Generation stopped by user]*"
                    final_text = (partial + stop_note) if partial else stop_note.strip()
        
                    try:
                        db_msg = Message(
                            team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                            sender_id=self.agent_id,
                            sender_name=self.name,
                            text=final_text,
                            reasoning_text=reasoning,
                        )
                        cleanup_db.add(db_msg)
                        await cleanup_db.commit()
                        await event_bus.publish(self.topic, {
                            "type": "message",
                            "id": str(db_msg.id),
                            "sender_id": self.agent_id,
                            "sender_name": self.name,
                            "role": self.role,
                            "text": final_text,
                            "has_reasoning": bool(reasoning),
                        })
                    except Exception as persist_err:
                        self._log.warning("Could not persist partial message after cancel: %s", persist_err)
        
                    # Signal idle so the UI clears the typing indicator
                    await event_bus.publish(self.topic, {
                        "type": "agent_status",
                        "sender_id": self.agent_id,
                        "sender_name": self.name,
                        "role": self.role,
                        "status": "idle",
                    })
                    
            # Launch cleanup as a background task so it isn't aborted by the current task's cancellation
            asyncio.create_task(_cleanup_cancelled_task())
            self._log.info("Agent %s stopped by user request.", self.name)
            raise  # re-raise so asyncio.Task knows it was cancelled
        finally:
            self._listening = False
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass

    async def _run_loop_inner(self, db_session: AsyncSession, initial_prompt: str, attachments: Optional[List[Dict]] = None, token: Optional["CancellationToken"] = None):
        # Fetch agent config
        agent_uuid = uuid.UUID(self.agent_id) if isinstance(self.agent_id, str) else self.agent_id
        stmt = select(Agent).where(Agent.id == agent_uuid)
        res = await db_session.execute(stmt)
        db_agent = res.scalar_one_or_none()

        # Safety guard: if agent was deleted mid-run, deny all non-safe tool access
        if db_agent is None:
            self._log.warning(
                "Agent record not found in DB during run_loop — may have been deleted. "
                "Restricting all tools to safe-only mode."
            )
            permissions = {"__deny_non_safe__": True}
        else:
            permissions = db_agent.tool_permissions or {}

        system_prompt = await self.assemble_system_prompt(db_session, initial_prompt)

        # Load conversation history for context continuity
        history = await self._load_conversation_history(db_session)

        # Build messages: history + new prompt
        content = [{"type": "text", "text": initial_prompt}]
        if attachments:
            for att in attachments:
                if att.get("type", "").startswith("image/"):
                    content.append({
                        "type": "image",
                        "local_path": att.get("local_path"),
                        "mime_type": att.get("type")
                    })
        
        messages = history + [{"role": "user", "content": content if attachments else initial_prompt}]

        loop_count = 0
        max_loops = getattr(core.config, "MAX_LOOPS", 10)

        # Emit agent status: active
        await event_bus.publish(self.topic, {
            "type": "agent_status",
            "sender_id": self.agent_id,
            "sender_name": self.name,
            "role": self.role,
            "status": "active",
        })

        self._current_thought_buffer = ""
        self._current_reasoning_buffer = ""

        while loop_count < max_loops:
            loop_count += 1

            await event_bus.publish(self.topic, {
                "type": "typing",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "role": self.role,
                "status": "thinking"
            })

            # Compaction Check
            compaction_threshold = getattr(core.config, "CONTEXT_COMPACTION_THRESHOLD", 15)
            if len(messages) > compaction_threshold:
                self._log.info("Context window growing large (%d msgs). Compacting...", len(messages))
                to_compact = messages[1:-5]
                try:
                    summary_prompt = COMPACTION_USER_PROMPT.format(context=json.dumps(to_compact))
                    summary = await llm_router.generate_completion(
                        model=getattr(core.config, "DEFAULT_FAST_MODEL", "openrouter/free"),
                        system_prompt=COMPACTION_SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": summary_prompt}],
                        temperature=0.3,
                        max_tokens=1000
                    )
                    messages = [messages[0]] + [{"role": "user", "content": f"[COMPACTED HISTORY]\n{summary}\n[/COMPACTED HISTORY]"}] + messages[-5:]
                except Exception as e:
                    self._log.warning("Compaction failed, continuing with full context: %s", e)

            # Stream completion with retry
            self._log.info("Thinking... (loop %d/%d)", loop_count, max_loops)

            # Emit explicit "thinking" status so the UI can show the indicator
            # before the first streamed chunk arrives.
            await event_bus.publish(self.topic, {
                "type": "agent_status",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "role": self.role,
                "status": "thinking",
            })

            thought_buffer = ""
            # Mirror buffers onto self so CancelledError handler can persist partial output
            # We save the reasoning trace accumulated so far (from previous loops) to restore it on retries
            saved_reasoning_buffer = self._current_reasoning_buffer
            had_error = False

            for attempt in range(3):
                try:
                    thought_buffer = ""
                    self._current_thought_buffer = ""
                    self._current_reasoning_buffer = saved_reasoning_buffer
                    
                    async for chunk in llm_router.generate_stream_with_reasoning(
                        model=self.model,
                        system_prompt=system_prompt,
                        messages=messages,
                        temperature=0.4,
                        project_id=self.project_id,
                        team_id=self.team_id,
                        agent_id=self.agent_id,
                        agent_name=self.name,
                        fallback_model=self.fallback_model,
                        reasoning_effort=self.reasoning_effort,
                    ):
                        content_chunk = chunk.get("content", "")
                        reasoning_chunk = chunk.get("reasoning", "")

                        if reasoning_chunk:
                            self._current_reasoning_buffer += reasoning_chunk
                            await event_bus.publish(self.topic, {
                                "type": "stream_reasoning",
                                "sender_id": self.agent_id,
                                "sender_name": self.name,
                                "role": self.role,
                                "chunk": reasoning_chunk,
                            })

                        if content_chunk:
                            thought_buffer += content_chunk
                            self._current_thought_buffer = thought_buffer
                            await event_bus.publish(self.topic, {
                                "type": "thought_delta",
                                "sender_id": self.agent_id,
                                "sender_name": self.name,
                                "role": self.role,
                                "delta": content_chunk
                            })
                    break  # Success
                except Exception as e:
                    if attempt < 2:
                        wait = (2 ** attempt) * 2
                        self._log.warning("LLM error (attempt %d): %s. Retrying in %ds...", attempt + 1, e, wait)
                        await asyncio.sleep(wait)
                    else:
                        had_error = True
                        error_msg = f"⚠️ LLM API error after 3 retries: {str(e)}"
                        self._log.error("LLM error after 3 retries: %s", e)
                        
                        db_msg = Message(
                            team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                            sender_id=self.agent_id,
                            sender_name=self.name,
                            text=error_msg,
                            reasoning_text=self._current_reasoning_buffer or None,
                        )
                        db_session.add(db_msg)
                        await db_session.commit()
                        
                        await event_bus.publish(self.topic, {
                            "type": "message",
                            "id": str(db_msg.id),
                            "sender_id": self.agent_id,
                            "sender_name": self.name,
                            "role": self.role,
                            "text": error_msg,
                            "has_reasoning": bool(self._current_reasoning_buffer)
                        })

            if had_error:
                break

            messages.append({"role": "assistant", "content": thought_buffer})

            # Strip any accidental "[Name]: " prefix the model may have
            # hallucinated at the start of its response.
            import re as _re
            thought_buffer = _re.sub(r'^\[[^\]]+\]:\s*', '', thought_buffer, count=1)

            action_call = self._parse_action(thought_buffer)

            if not action_call:
                # Agent is done — persist and broadcast
                self._log.info("Task finished after %d loops.", loop_count)
                db_msg = Message(
                    team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                    sender_id=self.agent_id,
                    sender_name=self.name, text=thought_buffer,
                    reasoning_text=self._current_reasoning_buffer or None,
                )
                db_session.add(db_msg)
                await db_session.commit()
                # Track the persisted message id for future file snapshots in this loop
                self.active_message_id = str(db_msg.id)

                await event_bus.publish(self.topic, {
                    "type": "message",
                    "id": str(db_msg.id),
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "text": thought_buffer,
                    "has_reasoning": bool(self._current_reasoning_buffer),
                })

                if self.parent_coordinator_id:
                    notification = self._build_task_notification(thought_buffer, "completed")
                    await event_bus.publish(self.topic, {
                        "type": "message",
                        "sender_id": self.agent_id,
                        "sender_name": self.name,
                        "role": self.role,
                        "text": notification,
                        "is_task_notification": True,
                    })

                await event_bus.publish(self.topic, {
                    "type": "agent_status",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "status": "idle",
                })
                break

            else:
                tool_name, tool_args = action_call
                self._log.info("Executing tool: %s", tool_name)

                # Move intermediate text to the reasoning trace
                self._current_reasoning_buffer += f"\n\n{thought_buffer}\n"
                
                await event_bus.publish(self.topic, {
                    "type": "collapse_to_reasoning",
                    "sender_id": self.agent_id,
                })

                await event_bus.publish(self.topic, {
                    "type": "agent_status",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "status": "executing_tool",
                    "tool_name": tool_name,
                })

                await event_bus.publish(self.topic, {
                    "type": "tool_start",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "tool_name": tool_name,
                    "arguments": tool_args
                })

                try:
                    args_str = json.dumps(tool_args, indent=2)
                except Exception:
                    args_str = str(tool_args)
                self._current_reasoning_buffer += f"\n🛠️ **{tool_name}**\n```json\n{args_str}\n```\n"

                try:
                    observation = await self._execute_tool(
                        name=tool_name, args=tool_args, permissions=permissions, token=token
                    )
                except Exception as e:
                    observation = f"✗ Tool Error: {str(e)}"
                    self._log.error("Tool '%s' raised exception: %s", tool_name, e)

                await event_bus.publish(self.topic, {
                    "type": "tool_end",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "tool_name": tool_name,
                    "observation": observation[:500]
                })
                
                self._current_reasoning_buffer += f"\n📄 **Result:**\n```\n{observation[:1000]}\n```\n"

                # Broadcast the intermediate trace row over WebSocket ONLY (no DB persistence)
                # is_intermediate=True so the UI renders it as a compact trace row while streaming
                intermediate_trace = (
                    f"🛠️ **{tool_name}**\n"
                    f"```json\n{args_str}\n```\n"
                    f"📄 **Result:**\n```\n{observation[:500]}\n```"
                )
                await event_bus.publish(self.topic, {
                    "type": "tool_trace",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "text": intermediate_trace,
                    "is_intermediate": True
                })

                messages.append({
                    "role": "user",
                    "content": f"[OBSERVATION] Tool output:\n{observation}\n[/OBSERVATION]"
                })
        
        # If we exited the loop by hitting max_loops, we still need to publish a final message
        if loop_count >= max_loops and action_call:
            self._log.warning("Agent hit max loop limit (%d). Terminating.", max_loops)
            final_note = f"\n\n*[System: Agent reached maximum loop limit of {max_loops}.]*"
            thought_buffer = self._current_thought_buffer + final_note
            
            db_msg = Message(
                team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                sender_id=self.agent_id,
                sender_name=self.name,
                text=thought_buffer,
                reasoning_text=self._current_reasoning_buffer or None,
            )
            db_session.add(db_msg)
            await db_session.commit()
            
            await event_bus.publish(self.topic, {
                "type": "message",
                "id": str(db_msg.id),
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "role": self.role,
                "text": thought_buffer,
                "has_reasoning": bool(self._current_reasoning_buffer),
            })
            await event_bus.publish(self.topic, {
                "type": "agent_status",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "role": self.role,
                "status": "idle",
            })

    def _parse_action(self, text: str) -> Any:
        """Parses [ACTION]tool_name(args)[/ACTION] or <tool_call>tool_name(args) even if truncated."""
        # First try to find a completed block
        match = re.search(r"(?:\[(?:ACTION|TOOL)\]|<tool_call>)\s*(\w+)\s*\((.*?)\)(?:\s*\[/(?:ACTION|TOOL)\]|\s*</tool_call>)", text, re.DOTALL)
        
        if match:
            tool_name = match.group(1)
            raw_args = match.group(2).strip()
        else:
            # Fallback for truncated streams (end of text)
            match = re.search(r"(?:\[(?:ACTION|TOOL)\]|<tool_call>)\s*(\w+)\s*\((.*)", text, re.DOTALL)
            if not match:
                return None
            tool_name = match.group(1)
            raw_args = match.group(2).strip()
            # Clean up trailing closing parens/tags if any
            raw_args = re.sub(r"\)\s*(?:\[/(?:ACTION|TOOL)\]|</tool_call>)?\s*$", "", raw_args).strip()
        
        try:
            arguments = json.loads(raw_args)
        except json.JSONDecodeError:
            arguments = {"value": raw_args}
        return tool_name, arguments

    def _build_task_notification(self, result_text: str, status: str) -> str:
        task_id = self.task_id or "unknown"
        result_summary = result_text[:1000] if len(result_text) > 1000 else result_text
        return (
            f"<task-notification>\n"
            f"  <task_id>{task_id}</task_id>\n"
            f"  <agent>{self.name}</agent>\n"
            f"  <status>{status}</status>\n"
            f"  <result>{result_summary}</result>\n"
            f"</task-notification>"
        )

    async def _listen_for_notifications(self):
        """
        Background listener that subscribes to the team EventBus and
        collects <task-notification> messages from worker agents.
        """
        topic = f"team:{self.team_id}"
        queue = await event_bus.subscribe(topic)

        try:
            while self._listening:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=2.0)

                    # Check if this is a task-notification from a worker
                    if (
                        event.get("type") == "message"
                        and event.get("is_task_notification")
                        and event.get("sender_id") != self.agent_id
                    ):
                        text = event.get("text", "")
                        notifications = self.parse_task_notifications(text)
                        for notif in notifications:
                            notif["agent"] = event.get("sender_name", "unknown")
                            self._worker_results.append(notif)
                            self._log.info(
                                "Collected notification from %s: task_id=%s status=%s",
                                notif.get("agent", "?"),
                                notif.get("task_id", "?"),
                                notif.get("status", "?"),
                            )

                    queue.task_done()
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            await event_bus.unsubscribe(topic, queue)

    async def collect_pending_notifications(self, timeout: float = 30.0) -> List[Dict[str, str]]:
        """
        Waits up to `timeout` seconds for worker notifications to arrive.
        Returns a list of parsed notification dicts.
        Used when the agent explicitly needs to wait for worker results.
        """
        collected = []
        # FIX: Use asyncio.get_running_loop() — asyncio.get_event_loop() is
        # deprecated in Python 3.10+ and raises DeprecationWarning.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while loop.time() < deadline:
            if self._worker_results:
                # Drain all pending results
                collected.extend(self._worker_results)
                self._worker_results.clear()
                break
            await asyncio.sleep(1.0)

        return collected

    def parse_task_notifications(self, text: str) -> List[Dict[str, str]]:
        """Parses <task-notification> XML blocks from worker messages."""
        notifications = []
        pattern = r"<task-notification>(.*?)</task-notification>"
        matches = re.findall(pattern, text, re.DOTALL)

        for match in matches:
            notification = {}
            for field in ["task_id", "agent", "status", "result", "tokens_used"]:
                field_match = re.search(f"<{field}>(.*?)</{field}>", match, re.DOTALL)
                if field_match:
                    notification[field] = field_match.group(1).strip()
            if notification:
                notifications.append(notification)

        return notifications

    async def _execute_tool(self, name: str, args: Dict[str, Any], permissions: Dict[str, str], token: Optional[CancellationToken] = None) -> str:
        # Safety: if agent was deleted mid-run, deny all non-safe tools
        if permissions.get("__deny_non_safe__"):
            from core.tools.tool_registry import ToolRegistry
            spec = ToolRegistry.get(name)
            if spec and spec.permission_default != "safe":
                self._log.warning(
                    "Denying tool '%s' (permission=%s) — agent record was deleted.",
                    name, spec.permission_default
                )
                return f"✗ Tool '{name}' denied: agent record no longer exists in the database."

        async def emit_progress(msg: str):
            await event_bus.publish(self.topic, {
                "type": "tool_progress",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "tool_name": name,
                "progress": msg
            })

        exec_context = ToolExecutionContext(
            agent_id=self.agent_id,
            agent_name=self.name,
            team_id=self.team_id,
            cancellation_token=token or CancellationToken(),
            emit_progress=emit_progress,
            active_message_id=self.active_message_id
        )
        
        # Build permission context
        perm_context = ToolPermissionContext(
            always_allow=set(),
            always_deny=set()
        )
        # Assuming permissions dict could have always_allow/always_deny lists
        if "always_allow" in permissions:
            perm_context.always_allow = set(permissions["always_allow"]) # type: ignore
        if "always_deny" in permissions:
            perm_context.always_deny = set(permissions["always_deny"]) # type: ignore

        from core.tools.tool_executor import tool_executor
        return await tool_executor.execute(
            tool_name=name, arguments=args,
            agent_id=self.agent_id, agent_name=self.name,
            team_id=self.team_id, permissions=permissions,
            active_message_id=self.active_message_id,
            context=exec_context,
            permission_context=perm_context
        )
