"""
# backend/core/chat/message_router.py

This file defines the router that parses and directs incoming messages.

Responsibilities:
1. Parse incoming text for @name (group tag) and /@name (private tag) mentions.
2. Support multiple @mentions in a single message (fan-out to multiple agents).
3. If no @mention, optionally route to the Coordinator agent.
4. Persist messages to the DB and broadcast via EventBus.
5. Trigger target Agent ReACT loops as background tasks.
"""

import re
import uuid
import asyncio
import logging
import weakref
from typing import Optional, List, Set, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("carole.message_router")

from core.chat.event_bus import event_bus
from core.memory.models import Agent, Message, Team, Project, User
from core.memory.database import async_session


class MessageRouter:
    def __init__(self):
        # Dict of agent_id -> set of running tasks.
        # Tracked so we can cancel specific agents on demand.
        self._running_tasks: Dict[str, Set[asyncio.Task]] = {}

    def cancel_agent(self, agent_id: str) -> int:
        """Cancel all active tasks for the given agent. Returns number of tasks cancelled."""
        tasks = self._running_tasks.get(agent_id, set())
        count = 0
        for task in list(tasks):
            if not task.done():
                task.cancel()
                count += 1
        logger.info("Cancelled %d task(s) for agent %s", count, agent_id)
        return count

    async def route_message(self, text: str, sender_id: str, team_id: str, sender_name: Optional[str] = None, attachments: Optional[List[Dict]] = None):
        """
        Parses a raw incoming message, persists it, and triggers agent ReACT loops
        based on @mention and /@private mention patterns.
        Supports multiple @mentions in a single message.
        """
        # Find all private mentions (/@name) and public mentions (@name)
        private_matches = re.findall(r"/\@(\w+)", text)
        public_matches = re.findall(r"(?<!/)@(\w+)", text)

        is_private = len(private_matches) > 0
        mentioned_names = private_matches if is_private else public_matches

        # Persist message to database
        async with async_session() as db:
            target_agents: List[Agent] = []
            recipient_id = None

            try:
                team_uuid = uuid.UUID(team_id)
            except (ValueError, AttributeError):
                logger.error("Invalid team_id in route_message: %s", team_id)
                return

            # Verify the team actually exists in the database
            stmt = select(Team.id).where(Team.id == team_uuid)
            result = await db.execute(stmt)
            if result.scalar_one_or_none() is None:
                logger.warning("Team %s not found. Dropping message from %s.", team_id, sender_id)
                return

            # OPTIMIZATION: Resolve all mentioned agents in a single query
            if mentioned_names:
                stmt = select(Agent).where(
                    Agent.team_id == team_uuid,
                    Agent.name.in_(mentioned_names)
                )
                result = await db.execute(stmt)
                agents = result.scalars().all()
                target_agents.extend(agents)
                if len(mentioned_names) == 1 and agents:
                    recipient_id = str(agents[0].id)

            resolved_sender_name = sender_name
            if sender_id == "human" and not resolved_sender_name:
                # OPTIMIZATION: Single joined query to resolve user's full name from team_uuid
                stmt = (
                    select(User)
                    .join(Project, Project.owner_id == User.id)
                    .join(Team, Team.project_id == Project.id)
                    .where(Team.id == team_uuid)
                )
                res = await db.execute(stmt)
                user = res.scalar_one_or_none()
                if user:
                    first = user.first_name or ""
                    last = user.last_name or ""
                    resolved_sender_name = f"{first} {last}".strip()

            if not resolved_sender_name and sender_id == "human":
                resolved_sender_name = "You"
            elif not resolved_sender_name:
                resolved_sender_name = sender_id

            # If no agents mentioned, route to Coordinator (if one exists)
            if not target_agents and sender_id == "human":
                stmt = select(Agent).where(
                    Agent.team_id == team_uuid,
                    Agent.role == "Coordinator"
                ).limit(1)
                result = await db.execute(stmt)
                coordinator = result.scalar_one_or_none()
                if coordinator:
                    target_agents.append(coordinator)
                else:
                    # Fallback: if no coordinator, route to all agents in the team
                    stmt = select(Agent).where(Agent.team_id == team_uuid)
                    result = await db.execute(stmt)
                    agents = result.scalars().all()
                    target_agents.extend(agents)

            # Save message to short-term memory
            db_msg = Message(
                team_id=team_uuid,
                sender_id=sender_id,
                sender_name=resolved_sender_name,
                recipient_id=recipient_id,
                is_private=is_private,
                text=text,
                attachments=attachments or []
            )
            db.add(db_msg)
            await db.commit()

            # Broadcast the message over the EventBus for all subscribers (UI + other agents)
            topic = f"team:{team_id}"
            await event_bus.publish(topic, {
                "type": "message",
                "id": str(db_msg.id),
                "sender_id": sender_id,
                "sender_name": resolved_sender_name,
                "recipient_id": recipient_id,
                "text": text,
                "is_private": is_private,
                "attachments": attachments or []
            })

            # Trigger all mentioned agents' ReACT loops
            for agent in target_agents:
                await self._trigger_agent(agent, text, db, attachments)

    async def _trigger_agent(self, agent: Agent, prompt_text: str, db_session: AsyncSession, attachments: Optional[List[Dict]] = None):
        """
        Spawns the target agent's ReACT loop as a background asyncio task.
        Holds a strong reference to the task to prevent silent GC before completion.
        Logs any unhandled exceptions that escape the agent loop.
        """
        # Resolve project_id through the team
        stmt = select(Team).where(Team.id == agent.team_id)
        result = await db_session.execute(stmt)
        team = result.scalar_one_or_none()
        project_id = str(team.project_id) if team else ""

        # Use Coordinator subclass for Coordinator role agents
        if agent.role == "Coordinator":
            from core.agent.coordinator import CoordinatorAgent
            react = CoordinatorAgent(
                agent_id=str(agent.id),
                team_id=str(agent.team_id),
                project_id=project_id,
                name=agent.name,
                role=agent.role,
                model=agent.model,
                system_prompt=agent.system_prompt,
                fallback_model=agent.fallback_model,
                reasoning_effort=getattr(agent, "reasoning_effort", "none") or "none",
            )
        else:
            from core.agent.react_agent import ReACTAgent
            react = ReACTAgent(
                agent_id=str(agent.id),
                team_id=str(agent.team_id),
                project_id=project_id,
                name=agent.name,
                role=agent.role,
                model=agent.model,
                system_prompt=agent.system_prompt,
                fallback_model=agent.fallback_model,
                reasoning_effort=getattr(agent, "reasoning_effort", "none") or "none",
            )

        # Run the agent loop in a fresh database session (separate transaction scope)
        async def _run_agent():
            async with async_session() as agent_db:
                await react.run_loop(agent_db, prompt_text, attachments)

        agent_id_str = str(agent.id)
        task = asyncio.create_task(_run_agent())

        # Track task per agent so it can be cancelled on demand
        self._running_tasks.setdefault(agent_id_str, set()).add(task)

        def _on_task_done(t: asyncio.Task):
            self._running_tasks.get(agent_id_str, set()).discard(t)
            if not t.cancelled():
                exc = t.exception()
                if exc:
                    logger.exception(
                        "Unhandled exception in agent loop for agent '%s': %s",
                        agent.name, exc, exc_info=exc
                    )

        task.add_done_callback(_on_task_done)


# Singleton
message_router = MessageRouter()
