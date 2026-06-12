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
from typing import Optional, List, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("carole.message_router")

from core.chat.event_bus import event_bus
from core.memory.models import Agent, Message, Team, Project, User
from core.memory.database import async_session


class MessageRouter:
    def __init__(self):
        # Weak set — tasks are tracked here so the GC doesn't silently collect
        # them before they finish, and we can log unhandled exceptions.
        self._running_tasks: Set[asyncio.Task] = set()

    async def route_message(self, text: str, sender_id: str, team_id: str, sender_name: Optional[str] = None):
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
            # Resolve all mentioned agents
            target_agents: List[Agent] = []
            recipient_id = None

            try:
                team_uuid = uuid.UUID(team_id)
            except (ValueError, AttributeError):
                logger.error("Invalid team_id in route_message: %s", team_id)
                return

            for name in mentioned_names:
                stmt = select(Agent).where(
                    Agent.team_id == team_uuid,
                    Agent.name == name
                )
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()
                if agent:
                    target_agents.append(agent)
                    if len(mentioned_names) == 1:
                        recipient_id = str(agent.id)

            resolved_sender_name = sender_name
            if sender_id == "human" and not resolved_sender_name:
                # FIX: use team_uuid (UUID type) — not the raw string — to match
                # the Team.id column which is stored as Uuid.
                stmt = select(Team).where(Team.id == team_uuid)
                res = await db.execute(stmt)
                team = res.scalar_one_or_none()
                if team:
                    stmt = select(Project).where(Project.id == team.project_id)
                    res = await db.execute(stmt)
                    project = res.scalar_one_or_none()
                    if project:
                        stmt = select(User).where(User.id == project.owner_id)
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
                )
                result = await db.execute(stmt)
                coordinator = result.scalar_one_or_none()
                if coordinator:
                    target_agents.append(coordinator)

            # Save message to short-term memory
            db_msg = Message(
                team_id=team_uuid,
                sender_id=sender_id,
                sender_name=resolved_sender_name,
                recipient_id=recipient_id,
                is_private=is_private,
                text=text
            )
            db.add(db_msg)
            await db.commit()

            # Broadcast the message over the EventBus for all subscribers (UI + other agents)
            topic = f"team:{team_id}"
            await event_bus.publish(topic, {
                "type": "message",
                "sender_id": sender_id,
                "sender_name": resolved_sender_name,
                "recipient_id": recipient_id,
                "text": text,
                "is_private": is_private,
            })

            # Trigger all mentioned agents' ReACT loops
            for agent in target_agents:
                await self._trigger_agent(agent, text, db)

    async def _trigger_agent(self, agent: Agent, prompt_text: str, db_session: AsyncSession):
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
            )

        # Run the agent loop in a fresh database session (separate transaction scope)
        async def _run_agent():
            async with async_session() as agent_db:
                await react.run_loop(agent_db, prompt_text)

        task = asyncio.create_task(_run_agent())
        # Hold a strong reference so the task is not silently GC'd
        self._running_tasks.add(task)

        def _on_task_done(t: asyncio.Task):
            self._running_tasks.discard(t)
            exc = t.exception() if not t.cancelled() else None
            if exc:
                logger.exception(
                    "Unhandled exception in agent loop for agent '%s': %s",
                    agent.name, exc, exc_info=exc
                )

        task.add_done_callback(_on_task_done)


# Singleton
message_router = MessageRouter()
