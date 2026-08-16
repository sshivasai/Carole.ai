"""
core/tools/cron_task_tools.py

Tools that allow agents to create, list, update, and delete their own scheduled cron tasks.
Agents can use these to automate recurring work (e.g. "check tech news every 2 minutes").
"""

import uuid
import logging
from datetime import timezone, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import async_session
from core.memory.models import ScheduledTask, Agent

logger = logging.getLogger("carole.cron_task_tools")


def _validate_cron(expression: str) -> tuple[bool, str]:
    """Basic validation for a 5-field cron expression."""
    try:
        from croniter import croniter
        if croniter.is_valid(expression):
            return True, ""
        return False, f"'{expression}' is not a valid cron expression."
    except ImportError:
        # If croniter not installed, let backend handle it
        parts = expression.strip().split()
        if len(parts) == 5:
            return True, ""
        return False, f"Cron expression must have 5 fields (got {len(parts)}). Example: '*/2 * * * *'"


def _fmt_task(task: ScheduledTask) -> dict:
    return {
        "id": str(task.id),
        "name": task.name,
        "agent_id": str(task.agent_id),
        "cron_expression": task.cron_expression,
        "prompt": task.prompt,
        "is_active": task.is_active,
        "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


class CronTaskTools:
    async def create_scheduled_task(
        self,
        agent_id: str,
        team_id: str,
        name: str,
        cron_expression: str,
        prompt: str,
    ) -> str:
        """Create a new scheduled task that triggers an agent on a cron schedule."""
        valid, err = _validate_cron(cron_expression)
        if not valid:
            return f"❌ Invalid cron expression: {err}\n\nExamples:\n  '*/2 * * * *'   → every 2 minutes\n  '0 9 * * 1-5'  → 9am on weekdays\n  '0 * * * *'    → every hour"

        try:
            async with async_session() as db:
                task = ScheduledTask(
                    team_id=uuid.UUID(team_id),
                    agent_id=uuid.UUID(agent_id),
                    name=name.strip(),
                    cron_expression=cron_expression.strip(),
                    prompt=prompt.strip(),
                    is_active=True,
                )
                db.add(task)
                await db.commit()
                await db.refresh(task)

                logger.info(
                    "[CronTaskTools] Agent %s created scheduled task '%s' (%s)",
                    agent_id, name, cron_expression
                )
                return (
                    f"✅ Scheduled task '{name}' created!\n"
                    f"  ID: {task.id}\n"
                    f"  Schedule: {cron_expression}\n"
                    f"  Status: Active\n"
                    f"  First run: at next matching time\n\n"
                    f"The cron worker will automatically trigger me with the specified prompt on schedule."
                )
        except Exception as e:
            logger.error("[CronTaskTools] Failed to create task: %s", e, exc_info=True)
            return f"❌ Failed to create scheduled task: {e}"

    async def list_scheduled_tasks(self, team_id: str) -> str:
        """List all scheduled tasks for the current team."""
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(ScheduledTask)
                    .where(ScheduledTask.team_id == uuid.UUID(team_id))
                    .order_by(ScheduledTask.created_at.desc())
                )
                tasks = result.scalars().all()

                if not tasks:
                    return "No scheduled tasks found for this team."

                lines = [f"📅 Scheduled Tasks ({len(tasks)} total):\n"]
                for t in tasks:
                    status = "🟢 Active" if t.is_active else "⏸ Paused"
                    last = t.last_run_at.strftime("%Y-%m-%d %H:%M UTC") if t.last_run_at else "Never"
                    lines.append(
                        f"  - [{status}] {t.name}\n"
                        f"      ID: {t.id}\n"
                        f"      Schedule: {t.cron_expression}\n"
                        f"      Last run: {last}\n"
                        f"      Prompt: {t.prompt[:80]}{'...' if len(t.prompt) > 80 else ''}\n"
                    )
                return "\n".join(lines)
        except Exception as e:
            logger.error("[CronTaskTools] list failed: %s", e, exc_info=True)
            return f"❌ Failed to list scheduled tasks: {e}"

    async def update_scheduled_task(
        self,
        task_id: str,
        is_active: bool | None = None,
        cron_expression: str | None = None,
        prompt: str | None = None,
        name: str | None = None,
    ) -> str:
        """Update a scheduled task (pause, resume, or change its schedule/prompt)."""
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(ScheduledTask).where(ScheduledTask.id == uuid.UUID(task_id))
                )
                task = result.scalar_one_or_none()
                if not task:
                    return f"❌ Scheduled task '{task_id}' not found."

                if is_active is not None:
                    task.is_active = is_active
                if cron_expression is not None:
                    valid, err = _validate_cron(cron_expression)
                    if not valid:
                        return f"❌ Invalid cron expression: {err}"
                    task.cron_expression = cron_expression.strip()
                if prompt is not None:
                    task.prompt = prompt.strip()
                if name is not None:
                    task.name = name.strip()

                await db.commit()
                await db.refresh(task)
                action = "resumed" if task.is_active else "paused"
                return f"✅ Scheduled task '{task.name}' updated. Status: {'🟢 Active' if task.is_active else '⏸ Paused'}."
        except Exception as e:
            logger.error("[CronTaskTools] update failed: %s", e, exc_info=True)
            return f"❌ Failed to update scheduled task: {e}"

    async def delete_scheduled_task(self, task_id: str) -> str:
        """Permanently delete a scheduled task."""
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(ScheduledTask).where(ScheduledTask.id == uuid.UUID(task_id))
                )
                task = result.scalar_one_or_none()
                if not task:
                    return f"❌ Scheduled task '{task_id}' not found."

                name = task.name
                await db.delete(task)
                await db.commit()
                return f"✅ Scheduled task '{name}' deleted."
        except Exception as e:
            logger.error("[CronTaskTools] delete failed: %s", e, exc_info=True)
            return f"❌ Failed to delete scheduled task: {e}"


cron_task_tools = CronTaskTools()
