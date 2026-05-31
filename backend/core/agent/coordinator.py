"""
# backend/core/agent/coordinator.py

Coordinator agent — the team lead who breaks down tasks, delegates to workers,
and synthesizes results. Subclasses ReACTAgent with Coordinator-specific behaviour.

Key differences from a Worker:
1. Has access to task management tools (create, assign, track).
2. Receives <task-notification> XML messages from workers and synthesizes them.
3. Plans before acting — breaks complex requests into sub-tasks.
4. Never delegates understanding — reads worker output and synthesizes.
"""

import json
import re
import asyncio
from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent.react_agent import ReACTAgent
from core.chat.event_bus import event_bus
from core.memory.models import Agent, Task, Message
from core.memory.database import async_session


class CoordinatorAgent(ReACTAgent):
    """Extended ReACT agent with Coordinator-specific planning and delegation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._worker_results: List[Dict[str, Any]] = []
        self._notification_queue: asyncio.Queue = asyncio.Queue()
        self._listening = False

    async def assemble_system_prompt(self, db_session: AsyncSession, current_task: str) -> str:
        """Extends the base prompt with coordinator-specific directives."""
        base_prompt = await super().assemble_system_prompt(db_session, current_task)

        # Fetch current team roster so the coordinator knows who's available
        stmt = select(Agent).where(Agent.team_id == self.team_id)
        result = await db_session.execute(stmt)
        teammates = result.scalars().all()

        roster_block = "\n<team-roster>\n"
        for agent in teammates:
            if str(agent.id) != self.agent_id:
                roster_block += f"- {agent.name} (Role: {agent.role}, Model: {agent.model})\n"
        roster_block += "</team-roster>\n"

        # Fetch active tasks
        task_stmt = select(Task).where(
            Task.team_id == self.team_id,
            Task.status.in_(["todo", "in_progress", "review"])
        )
        task_result = await db_session.execute(task_stmt)
        active_tasks = task_result.scalars().all()

        tasks_block = ""
        if active_tasks:
            tasks_block = "\n<active-tasks>\n"
            for t in active_tasks:
                assignee = t.assigned_agent_id or "unassigned"
                tasks_block += f"- [{t.status}] {t.title} (priority: {t.priority}, assigned: {assignee})\n"
            tasks_block += "</active-tasks>\n"

        # Include any collected worker notifications from previous iterations
        worker_results_block = ""
        if self._worker_results:
            worker_results_block = "\n<worker-reports>\n"
            for wr in self._worker_results:
                worker_results_block += (
                    f"- Agent: {wr.get('agent', 'unknown')}, Task: {wr.get('task_id', 'unknown')}, "
                    f"Status: {wr.get('status', 'unknown')}\n"
                    f"  Result: {wr.get('result', 'No result')[:500]}\n"
                )
            worker_results_block += "</worker-reports>\n"

        coordinator_directives = (
            "\n<coordinator-directives>\n"
            "You are the COORDINATOR. Your job is to:\n"
            "1. Break complex requests into concrete sub-tasks.\n"
            "2. Assign tasks to the right teammate based on their role.\n"
            "3. Use spawn_agent to kick off a worker, or send_message to continue one.\n"
            "4. When workers finish, they send <task-notification> messages. Read them carefully.\n"
            "5. NEVER delegate understanding. After a worker reports back, synthesize their findings.\n"
            "6. Track progress with create_task / update_task tools.\n"
            "7. When everything is done, summarize the results to the team.\n"
            "</coordinator-directives>\n"
        )

        return f"{base_prompt}\n{roster_block}\n{tasks_block}\n{worker_results_block}\n{coordinator_directives}"

    async def run_loop(self, db_session: AsyncSession, initial_prompt: str):
        """
        Overrides the base ReACT loop to add worker notification collection.
        After spawning workers, the coordinator periodically collects
        <task-notification> messages and injects them into its context.
        """
        # Start listening for task notifications on the team topic
        self._listening = True
        listener_task = asyncio.create_task(self._listen_for_notifications())

        try:
            await super().run_loop(db_session, initial_prompt)
        finally:
            self._listening = False
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass

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
                            print(
                                f"📋 [Coordinator: {self.name}] Collected notification from "
                                f"{notif['agent']}: task_id={notif.get('task_id', '?')}, "
                                f"status={notif.get('status', '?')}"
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
        Used when the coordinator explicitly needs to wait for worker results.
        """
        collected = []
        deadline = asyncio.get_event_loop().time() + timeout

        while asyncio.get_event_loop().time() < deadline:
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
