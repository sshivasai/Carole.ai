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
from core.memory.models import Learning, Message, Agent, Project, User
from core.tools.tool_registry import ToolRegistry
from core.config import (
    STRICT_REASONING_GUIDELINES, KEYWORD_EXTRACTION_PROMPT,
    CONTEXT_COMPACTION_THRESHOLD, COMPACTION_SYSTEM_PROMPT,
    COMPACTION_USER_PROMPT, DEFAULT_FAST_MODEL, MEMORY_RETRIEVAL_LIMIT
)

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
        """Assembles system prompt with learnings, tools, team roster, and reasoning guidelines."""
        from sqlalchemy import func

        # 0. Fetch current team roster so the agent knows who is available
        stmt = select(Agent).where(Agent.team_id == self.team_id)
        roster_result = await db_session.execute(stmt)
        teammates = roster_result.scalars().all()

        roster_block = "\n<team-roster>\n"
        for teammate in teammates:
            if str(teammate.id) != self.agent_id:
                roster_block += f"- {teammate.name} (Role: {teammate.role})\n"
        roster_block += "</team-roster>\n"

        # 0.5 Fetch human user context
        human_context = ""
        project_result = await db_session.execute(select(Project).where(Project.id == self.project_id))
        project = project_result.scalar_one_or_none()
        if project:
            user_result = await db_session.execute(select(User).where(User.id == project.owner_id))
            user = user_result.scalar_one_or_none()
            if user:
                first = user.first_name or ""
                last = user.last_name or ""
                full_name = f"{first} {last}".strip() or "Unknown User"
                human_context = f"\n<human-context>\nThe human user / project owner is {full_name}.\n</human-context>\n"

        # 1. Generate search embeddings
        query_vector = await llm_router.generate_embeddings(current_task)

        # 2. Extract concise keywords for the Sparse (Lexical) Search component
        keyword_prompt = KEYWORD_EXTRACTION_PROMPT.format(task=current_task)
        try:
            keywords = await llm_router.generate_completion(
                model=DEFAULT_FAST_MODEL,
                system_prompt="You are a keyword extractor.",
                messages=[{"role": "user", "content": keyword_prompt}],
                temperature=0.1,
                max_tokens=20
            )
            # Clean up punctuation and newlines
            keywords = keywords.replace('"', '').replace(',', '').strip()
        except Exception:
            keywords = current_task[:50]  # Fallback

        # 3. Hybrid Search: Combine pgvector Cosine Distance with PostgreSQL tsvector Full-Text Search
        # We want to match exact technical keywords (Sparse) while still understanding concepts (Dense).
        # We parse the LLM-extracted keywords into an OR-based text query (word1 | word2 | word3)
        or_query = ' | '.join(keywords.split())
        ts_query = func.to_tsquery('english', or_query)
        ts_vector = func.to_tsvector('english', Learning.task_summary.concat(' ').concat(Learning.lesson_rule))
        ts_rank = func.ts_rank_cd(ts_vector, ts_query)

        # Hybrid Score: Cosine distance is lower=better (0 to 2). Rank is higher=better.
        # We subtract rank to boost exact keyword matches to the top of the semantic results.
        hybrid_order = Learning.embedding.cosine_distance(query_vector) - (ts_rank * 0.5)

        stmt = (
            select(Learning)
            .where(Learning.project_id == self.project_id)
            .where(or_(Learning.team_id == None, Learning.team_id == self.team_id))
            .order_by(hybrid_order)
            .limit(MEMORY_RETRIEVAL_LIMIT)
        )
        res = await db_session.execute(stmt)
        past_learnings = res.scalars().all()

        # 4. Format past learnings
        learnings_block = ""
        if past_learnings:
            learnings_block = "\n<lessons-learned>\n"
            for learning in past_learnings:
                learnings_block += f"- Task context: {learning.task_summary}\n  Lesson: {learning.lesson_rule}\n"
            learnings_block += "</lessons-learned>\n"

        # 3. Tool list
        tools_block = "\n" + ToolRegistry.to_llm_prompt(team_id=str(self.team_id), agent_id=str(self.agent_id)) + "\n"

        # 4. Reasoning guidelines
        return f"{self.system_prompt}\n{roster_block}\n{human_context}\n{learnings_block}\n{tools_block}\n{STRICT_REASONING_GUIDELINES}"

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

            # Compaction Check
            if len(messages) > CONTEXT_COMPACTION_THRESHOLD:
                print(f"🗜️ [Agent: {self.name}] Context window growing large. Compacting...")
                to_compact = messages[1:-5]
                try:
                    summary_prompt = COMPACTION_USER_PROMPT.format(context=json.dumps(to_compact))
                    summary = await llm_router.generate_completion(
                        model=DEFAULT_FAST_MODEL,
                        system_prompt=COMPACTION_SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": summary_prompt}],
                        temperature=0.3,
                        max_tokens=1000
                    )
                    messages = [messages[0]] + [{"role": "user", "content": f"[COMPACTED HISTORY]\n{summary}\n[/COMPACTED HISTORY]"}] + messages[-5:]
                except Exception as e:
                    print(f"⚠️ [Agent: {self.name}] Compaction failed, continuing with full context: {e}")

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
