"""
# backend/core/chat/message_router.py

This file defines the router that parses and directs incoming messages.

Responsibilities:
1. Parse incoming text for @name (group tag) and /@name (private tag) mentions.
2. If @name is used, push the message to the public Team thread in the DB and alert the agent.
3. If /@name is used, push the message to the Agent's private memory thread ONLY.
4. Trigger the target Agent's ReACT loop via the EventBus.
"""

import re
import asyncio
from typing import Optional
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
        """
        # Determine if it is a private message (/@name) or a public mention (@name)
        private_match = re.search(r"/\@(\w+)", text)
        public_match = re.search(r"(?<!/)\@(\w+)", text)

        recipient_id = None
        target_agent_name = None
        is_private = False

        if private_match:
            target_agent_name = private_match.group(1)
            is_private = True
        elif public_match:
            target_agent_name = public_match.group(1)

        # Persist message to database
        async with async_session() as db:
            # Resolve agent if mentioned
            target_agent = None
            if target_agent_name:
                stmt = select(Agent).where(
                    Agent.team_id == team_id,
                    Agent.name == target_agent_name
                )
                result = await db.execute(stmt)
                target_agent = result.scalar_one_or_none()
                if target_agent:
                    recipient_id = str(target_agent.id)

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
                "recipient_id": recipient_id,
                "text": text,
                "is_private": is_private,
            })

            # If a valid agent was mentioned, trigger their ReACT loop
            if target_agent:
                await self._trigger_agent(target_agent, text, db)

    async def _trigger_agent(self, agent: Agent, prompt_text: str, db_session: AsyncSession):
        """
        Spawns the target agent's ReACT loop as a background asyncio task so it
        runs concurrently without blocking the message router or the WebSocket handler.
        """
        from core.agent.react_agent import ReACTAgent

        # Resolve project_id through the team
        stmt = select(Team).where(Team.id == agent.team_id)
        result = await db_session.execute(stmt)
        team = result.scalar_one_or_none()
        project_id = str(team.project_id) if team else ""

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
