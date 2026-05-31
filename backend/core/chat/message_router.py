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
import asyncio
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.chat.event_bus import event_bus
from core.memory.models import Agent, Message, Team
from core.memory.database import async_session


class MessageRouter:
    def __init__(self):
        pass

    async def route_message(self, text: str, sender_id: str, team_id: str):
        """
        Parses a raw incoming message, persists it, and triggers agent ReACT loops
        based on @mention and /@private mention patterns.
        Supports multiple @mentions in a single message.
        """
        # Find all private mentions (/@name) and public mentions (@name)
        private_matches = re.findall(r"/\@(\w+)", text)
        public_matches = re.findall(r"(?<!/)\@(\w+)", text)

        is_private = len(private_matches) > 0
        mentioned_names = private_matches if is_private else public_matches

        # Persist message to database
        async with async_session() as db:
            # Resolve all mentioned agents
            target_agents: List[Agent] = []
            recipient_id = None

            for name in mentioned_names:
                stmt = select(Agent).where(
                    Agent.team_id == team_id,
                    Agent.name == name
                )
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()
                if agent:
                    target_agents.append(agent)
                    if len(mentioned_names) == 1:
                        recipient_id = str(agent.id)

            # If no agents mentioned, route to Coordinator (if one exists)
            if not target_agents and sender_id == "human":
                stmt = select(Agent).where(
                    Agent.team_id == team_id,
                    Agent.role == "Coordinator"
                )
                result = await db.execute(stmt)
                coordinator = result.scalar_one_or_none()
                if coordinator:
                    target_agents.append(coordinator)

            # Save message to short-term memory
            db_msg = Message(
                team_id=team_id,
                sender_id=sender_id,
                recipient_id=recipient_id,
                text=text
            )
            db.add(db_msg)
            await db.commit()

            # Broadcast the message over the EventBus for all subscribers (UI + other agents)
            topic = f"team:{team_id}"
            await event_bus.publish(topic, {
                "type": "message",
                "sender_id": sender_id,
                "sender_name": "You" if sender_id == "human" else sender_id,
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
        Uses CoordinatorAgent for Coordinator role, ReACTAgent for others.
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

        asyncio.create_task(_run_agent())


# Singleton
message_router = MessageRouter()
