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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent.react_agent import ReACTAgent
from core.memory.models import Task
from core.config import COORDINATOR_DIRECTIVES


class CoordinatorAgent(ReACTAgent):
    """Extended ReACT agent with Coordinator-specific planning and delegation."""

    async def assemble_system_prompt(self, db_session: AsyncSession, current_task: str) -> str:
        """Extends the base prompt with coordinator-specific directives."""
        base_prompt = await super().assemble_system_prompt(db_session, current_task)

        # Fetch active tasks
        import uuid
        team_uuid = uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id
        task_stmt = select(Task).where(
            Task.team_id == team_uuid,
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

        return f"{base_prompt}\n{tasks_block}\n{COORDINATOR_DIRECTIVES}"
