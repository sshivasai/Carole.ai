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

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent.react_agent import ReACTAgent
from core.memory.models import Task
from core.config import COORDINATOR_DIRECTIVES
from core.agent.prompt_safety import reference_block


class CoordinatorAgent(ReACTAgent):
    """Extended ReACT agent with Coordinator-specific planning and delegation."""

    async def assemble_system_prompt(self, db_session: AsyncSession, current_task: str) -> str:
        """Extends the base prompt with coordinator-specific directives.

        IMPORTANT: COORDINATOR_DIRECTIVES are injected BEFORE the capabilities/tools
        block (which is assembled by super()). This ensures the coordinator's core
        instructions are not buried after a long tool list in extended contexts.
        """
        from core.agent.context_compiler import CHAT, budget_records
        if getattr(self, "_context_policy", None) == CHAT:
            return await super().assemble_system_prompt(db_session, current_task)
        if self._cached_system_prompt is not None and self._cached_system_prompt_task == current_task:
            return self._cached_system_prompt
        # Build the coordinator prefix: directives + active task board
        team_uuid = uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id
        task_stmt = select(Task).where(
            Task.team_id == team_uuid,
            Task.status.in_(["todo", "in_progress", "review"])
        )
        task_stmt = task_stmt.order_by(Task.id).limit(100)
        task_result = await db_session.execute(task_stmt)
        active_tasks = task_result.scalars().all()

        tasks_block = ""
        if active_tasks:
            tasks_block = "\n<active-tasks>\n"
            for t in active_tasks:
                assignee = t.assigned_agent_id or "unassigned"
                tasks_block += f"- [{t.status}] {str(t.title)[:500]} (priority: {t.priority}, assigned: {assignee})\n"
            tasks_block += "</active-tasks>\n"

        # Prepend coordinator directives to the system prompt (before tool capabilities),
        # then let the base class append the full capabilities block (tools, memory, browser, etc.)
        coordinator_prefix = "" if COORDINATOR_DIRECTIVES in (self.system_prompt or "") else COORDINATOR_DIRECTIVES + "\n"

        # Temporarily inject the prefix into self.system_prompt so assemble_system_prompt
        # includes it at the top of the assembled output, before the capabilities block.
        original_system_prompt = self.system_prompt
        self.system_prompt = coordinator_prefix + (self.system_prompt or "")
        try:
            assembled = await super().assemble_system_prompt(db_session, current_task)
            if tasks_block:
                assembled += reference_block("active task board", budget_records(
                    tasks_block.splitlines(), 800, current_task, self.model))
            self._cached_system_prompt = assembled
            return assembled
        finally:
            self.system_prompt = original_system_prompt


# Canonical role name alias
OrchestratorAgent = CoordinatorAgent
