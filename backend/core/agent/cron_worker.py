"""
# backend/core/agent/cron_worker.py

Background worker that evaluates ScheduledTasks and triggers agents.
"""

import asyncio
import logging
from datetime import datetime, timezone
from croniter import croniter
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import async_session
from core.memory.models import ScheduledTask, Agent, Team
from core.chat.event_bus import event_bus

logger = logging.getLogger("carole.cron")

class AgentCronWorker:
    """
    Background worker that checks for due scheduled tasks every 60 seconds
    and dispatches a system prompt to the assigned agent via the EventBus.
    """

    def __init__(self, interval_seconds: int = 60):
        self._interval_seconds = interval_seconds
        self._running = False

    async def start(self):
        self._running = True
        logger.info("⏱️ [Cron Worker] Started. Checking schedule every %d seconds.", self._interval_seconds)

        while self._running:
            cycle_start = asyncio.get_running_loop().time()
            try:
                await self._check_schedule()
            except Exception as e:
                logger.error("[Cron Worker] Error during cycle: %s", e, exc_info=True)

            elapsed = asyncio.get_running_loop().time() - cycle_start
            sleep_time = max(0, self._interval_seconds - elapsed)
            await asyncio.sleep(sleep_time)

    def stop(self):
        self._running = False
        logger.info("[Cron Worker] Stopped.")

    async def _check_schedule(self):
        now = datetime.now(timezone.utc)

        async with async_session() as db:
            # Fetch all active scheduled tasks
            stmt = select(ScheduledTask).where(ScheduledTask.is_active == True)
            result = await db.execute(stmt)
            tasks = result.scalars().all()

            for task in tasks:
                if not task.cron_expression:
                    continue

                try:
                    # croniter expects naive datetimes or aware datetimes. Using aware.
                    base_time = task.last_run_at or task.created_at
                    # Make sure base_time is aware if it's not
                    if base_time.tzinfo is None:
                        base_time = base_time.replace(tzinfo=timezone.utc)
                    
                    cron = croniter(task.cron_expression, base_time)
                    next_run = cron.get_next(datetime)

                    # If the next run time has passed (is in the past relative to `now`), we should trigger it
                    if next_run <= now:
                        logger.info(f"[Cron Worker] Triggering task '{task.name}' for agent {task.agent_id}")
                        await self._trigger_agent(db, task, now)
                except Exception as e:
                    logger.error(f"[Cron Worker] Failed to evaluate/trigger task {task.id}: {e}", exc_info=True)


    async def _trigger_agent(self, db: AsyncSession, task: ScheduledTask, trigger_time: datetime):
        # Update last_run_at
        task.last_run_at = trigger_time
        await db.commit()
        await db.refresh(task)

        from core.chat.message_router import message_router
        
        # We need the agent's name to mention them, or we can just prepend /@agent_name
        # Wait, if we only have task.agent_id, we can look up the agent.
        agent_stmt = select(Agent).where(Agent.id == task.agent_id)
        res = await db.execute(agent_stmt)
        agent = res.scalar_one_or_none()
        agent_name_mention = f"/@{agent.name} " if agent else ""
        
        text = f"{agent_name_mention}[SYSTEM SCHEDULED TASK: {task.name}]\n{task.prompt}"
        
        # Route the message which saves it to the DB and triggers the agent
        await message_router.route_message(
            text=text,
            sender_id="system",
            team_id=str(task.team_id),
            sender_name="System Scheduler",
        )
        
        # 4. Create a Notification record for the scheduled task
        # We need to find a user_id to notify. 
        # A scheduled task belongs to a team, which belongs to a project, which belongs to a user.
        from core.memory.models import Team, Project, Notification
        stmt = (
            select(Project.owner_id)
            .join(Team, Team.project_id == Project.id)
            .where(Team.id == task.team_id)
        )
        owner_id_res = await db.execute(stmt)
        owner_id = owner_id_res.scalar_one_or_none()
        
        if owner_id:
            notification = Notification(
                user_id=str(owner_id),
                title="Scheduled Task Triggered",
                message=f"Task '{task.name}' has been triggered and routed to agent {agent.name if agent else 'Unknown'}.",
                type="info"
            )
            db.add(notification)
            await db.commit()

# Singleton instance
cron_worker = AgentCronWorker()
