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

import json
import re
import asyncio
from typing import List, Dict, Any, Optional
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm.multi_model_router import llm_router
from core.chat.event_bus import event_bus
from core.memory.models import Learning, Message, Agent
from core.tools.tool_registry import ToolRegistry


class ReACTAgent:
    def __init__(
        self, agent_id: str, team_id: str, project_id: str,
        name: str, role: str, model: str, system_prompt: str,
        parent_coordinator_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.team_id = team_id
        self.project_id = project_id
        self.name = name
        self.role = role
        self.model = model
        self.system_prompt = system_prompt
        self.topic = f"team:{self.team_id}"
        self.parent_coordinator_id = parent_coordinator_id
        self.task_id = task_id

    async def _load_conversation_history(self, db_session: AsyncSession, limit: int = 20) -> List[Dict[str, str]]:
        """Loads recent team messages from the DB to give the agent conversation context."""
        stmt = (
            select(Message)
            .where(Message.team_id == self.team_id)
            .where(
                or_(
                    Message.is_private == False,
                    Message.recipient_id == self.agent_id,
                    Message.sender_id == self.agent_id
                )
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await db_session.execute(stmt)
        messages = list(reversed(result.scalars().all()))

        history = []
        for msg in messages:
            role = "assistant" if msg.sender_id == self.agent_id else "user"
            sender_label = msg.sender_name or msg.sender_id
            history.append({
                "role": role,
                "content": f"[{sender_label}]: {msg.text}"
            })
        return history

    async def assemble_system_prompt(self, db_session: AsyncSession, current_task: str) -> str:
        """Assembles system prompt with learnings, tools, and reasoning guidelines."""
        # 1. Fetch top 3 semantically relevant "Lessons Learned" from pgvector
        query_vector = await llm_router.generate_embeddings(current_task)

        stmt = (
            select(Learning)
            .where(Learning.project_id == self.project_id)
            .where(or_(Learning.team_id == None, Learning.team_id == self.team_id))
            .order_by(Learning.embedding.cosine_distance(query_vector))
            .limit(3)
        )
        res = await db_session.execute(stmt)
        past_learnings = res.scalars().all()

        # 2. Format past learnings
        learnings_block = ""
        if past_learnings:
            learnings_block = "\n<lessons-learned>\n"
            for learning in past_learnings:
                learnings_block += f"- Task context: {learning.task_summary}\n  Lesson: {learning.lesson_rule}\n"
            learnings_block += "</lessons-learned>\n"

        # 3. Tool list
        tools_block = "\n" + ToolRegistry.to_llm_prompt() + "\n"

        # 4. Reasoning guidelines
        research_directives = (
            "\n<strict-reasoning-guidelines>\n"
            "1. CONFIDENCE ASSESSMENT: If your internal data is old or missing, call `web_search` or `web_fetch` first.\n"
            "2. WEB CITATIONS: When using web data, include source URLs in your response.\n"
            "3. TOOL CALLS: Use [ACTION]tool_name({\"param\": \"value\"})[/ACTION] to invoke tools.\n"
            "4. NATURAL SPEECH: Talk like a real dev in a team chat. Be concise and direct.\n"
            "5. When done, just say your final answer — no [ACTION] tag means you're finished.\n"
            "</strict-reasoning-guidelines>\n"
        )

        return f"{self.system_prompt}\n{learnings_block}\n{tools_block}\n{research_directives}"

    async def run_loop(self, db_session: AsyncSession, initial_prompt: str):
        """Runs the core ReACT loop with conversation history and streaming."""
        # Fetch agent config
        stmt = select(Agent).where(Agent.id == self.agent_id)
        res = await db_session.execute(stmt)
        db_agent = res.scalar_one_or_none()
        permissions = db_agent.tool_permissions if db_agent else {}

        system_prompt = await self.assemble_system_prompt(db_session, initial_prompt)

        # Load conversation history for context continuity
        history = await self._load_conversation_history(db_session)

        # Build messages: history + new prompt
        messages = history + [{"role": "user", "content": initial_prompt}]

        loop_count = 0
        max_loops = 10

        # Emit agent status: active
        await event_bus.publish(self.topic, {
            "type": "agent_status",
            "sender_id": self.agent_id,
            "sender_name": self.name,
            "role": self.role,
            "status": "active",
        })

        while loop_count < max_loops:
            loop_count += 1

            await event_bus.publish(self.topic, {
                "type": "typing",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "role": self.role,
                "status": "thinking"
            })

            # Stream completion with retry
            print(f"🤖 [Agent: {self.name}] Thinking... (loop {loop_count})")
            thought_buffer = ""
            had_error = False

            for attempt in range(3):
                try:
                    thought_buffer = ""
                    async for chunk in llm_router.generate_stream(
                        model=self.model,
                        system_prompt=system_prompt,
                        messages=messages,
                        temperature=0.4,
                        project_id=self.project_id,
                        team_id=self.team_id,
                        agent_id=self.agent_id,
                        agent_name=self.name
                    ):
                        thought_buffer += chunk
                        await event_bus.publish(self.topic, {
                            "type": "thought_delta",
                            "sender_id": self.agent_id,
                            "sender_name": self.name,
                            "role": self.role,
                            "delta": chunk
                        })
                    break  # Success
                except Exception as e:
                    if attempt < 2:
                        wait = (2 ** attempt) * 2
                        print(f"⚠️ [Agent: {self.name}] LLM error: {e}. Retrying in {wait}s...")
                        await asyncio.sleep(wait)
                    else:
                        had_error = True
                        error_msg = f"⚠️ LLM API error after 3 retries: {str(e)}"
                        await event_bus.publish(self.topic, {
                            "type": "message",
                            "sender_id": self.agent_id,
                            "sender_name": self.name,
                            "role": self.role,
                            "text": error_msg
                        })

            if had_error:
                break

            messages.append({"role": "assistant", "content": thought_buffer})

            action_call = self._parse_action(thought_buffer)

            if not action_call:
                # Agent is done — persist and broadcast
                print(f"✓ [Agent: {self.name}] Task finished.")
                db_msg = Message(
                    team_id=self.team_id, sender_id=self.agent_id,
                    sender_name=self.name, text=thought_buffer
                )
                db_session.add(db_msg)
                await db_session.commit()

                await event_bus.publish(self.topic, {
                    "type": "message",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "text": thought_buffer
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
                print(f"🛠️ [Agent: {self.name}] Tool: {tool_name}")

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
                    observation = await self._execute_tool(
                        name=tool_name, args=tool_args, permissions=permissions
                    )
                except Exception as e:
                    observation = f"✗ Tool Error: {str(e)}"

                await event_bus.publish(self.topic, {
                    "type": "tool_end",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "tool_name": tool_name,
                    "observation": observation[:500]
                })

                messages.append({
                    "role": "user",
                    "content": f"[OBSERVATION] Tool output:\n{observation}\n[/OBSERVATION]"
                })

    def _parse_action(self, text: str) -> Any:
        """Parses [ACTION]tool_name(args)[/ACTION] from generated text."""
        match = re.search(r"\[ACTION\](\w+)\((.*?)\)\[/ACTION\]", text, re.DOTALL)
        if match:
            tool_name = match.group(1)
            raw_args = match.group(2).strip()
            try:
                arguments = json.loads(raw_args)
            except json.JSONDecodeError:
                arguments = {"value": raw_args}
            return tool_name, arguments
        return None

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

    async def _execute_tool(self, name: str, args: Dict[str, Any], permissions: Dict[str, str]) -> str:
        from core.tools.tool_executor import tool_executor
        return await tool_executor.execute(
            tool_name=name, arguments=args,
            agent_id=self.agent_id, agent_name=self.name,
            team_id=self.team_id, permissions=permissions
        )
