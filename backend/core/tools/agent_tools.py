"""
# backend/core/tools/agent_tools.py

Tools for inter-agent delegation and coordination.

- spawn_agent: Creates a new ReACT loop for a named agent in the same team.
  Now supports parent_coordinator_id and auto-generated task_id for the
  <task-notification> protocol.
- send_message: Publishes a message to the team EventBus, optionally targeting a specific agent.
"""

import uuid
import asyncio
from typing import Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.chat.event_bus import event_bus
from core.memory.database import async_session
from core.memory.models import Agent, Team, Message


class AgentTools:
    async def spawn_agent(
        self,
        agent_name: str,
        task: str,
        team_id: str,
        parent_coordinator_id: Optional[str] = None,
    ) -> str:
        """
        Looks up an agent by name within the team and spawns its ReACT loop
        as a background task with the given task prompt.

        If parent_coordinator_id is provided, the spawned worker will send
        a <task-notification> XML back to the coordinator upon completion.
        """
        async with async_session() as db:
            stmt = select(Agent).where(Agent.team_id == team_id, Agent.name == agent_name)
            result = await db.execute(stmt)
            agent = result.scalar_one_or_none()

            if not agent:
                return f"Error: No agent named '{agent_name}' found in this team."

            # Resolve project_id
            team_stmt = select(Team).where(Team.id == team_id)
            team_result = await db.execute(team_stmt)
            team = team_result.scalar_one_or_none()
            project_id = str(team.project_id) if team else ""

        # Generate a unique task_id for tracking this delegation
        task_id = str(uuid.uuid4())

        # Lazy import to avoid circular dependency
        from core.agent.react_agent import ReACTAgent

        react = ReACTAgent(
            agent_id=str(agent.id),
            team_id=str(agent.team_id),
            project_id=project_id,
            name=agent.name,
            role=agent.role,
            model=agent.model,
            system_prompt=agent.system_prompt,
            parent_coordinator_id=parent_coordinator_id,
            task_id=task_id,
        )

        async def _run():
            async with async_session() as agent_db:
                await react.run_loop(agent_db, task)

        asyncio.create_task(_run())

        status_msg = f"Success: Spawned agent '{agent_name}' with task: {task[:100]}"
        if parent_coordinator_id:
            status_msg += f" (task_id={task_id}, will notify coordinator on completion)"
        return status_msg

    async def send_message(self, text: str, sender_id: str, team_id: str, recipient_name: str = None) -> str:
        """
        Publishes a message to the team EventBus. If recipient_name is given,
        sets the routing key so only that agent picks it up.
        """
        recipient_id = None
        if recipient_name:
            async with async_session() as db:
                stmt = select(Agent).where(Agent.team_id == team_id, Agent.name == recipient_name)
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()
                if agent:
                    recipient_id = str(agent.id)

        # Persist
        async with async_session() as db:
            db.add(Message(
                team_id=team_id,
                sender_id=sender_id,
                recipient_id=recipient_id,
                text=text,
            ))
            await db.commit()

        # Broadcast
        await event_bus.publish(f"team:{team_id}", {
            "type": "message",
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "text": text,
        })
        return "Message sent."


# Singleton
agent_tools = AgentTools()
