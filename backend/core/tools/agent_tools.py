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
from core.config import DEFAULT_FAST_MODEL


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

    async def hire_subagent(self, role: str, expertise: str, task: str, team_id: str, _agent_id: str, model: str = None) -> str:
        """
        Dynamically creates a new subagent row in the database and spawns its loop asynchronously.
        Returns a string confirming successful hiring.
        """
        subagent_name = f"Subagent-{role.replace(' ', '')}"
        sys_prompt = f"You are a temporary subagent. Your role is: {role}.\nYour expertise: {expertise}\nYou must complete the given task and return the result."
        
        async with async_session() as db:
            # Check for existing agent just in case (optional, we could generate unique names)
            stmt = select(Agent).where(Agent.team_id == team_id, Agent.name == subagent_name)
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                # Append a random UUID suffix to make it unique if a subagent for this role exists
                subagent_name = f"{subagent_name}-{str(uuid.uuid4())[:4]}"

            new_agent = Agent(
                team_id=team_id,
                name=subagent_name,
                role=role,
                system_prompt=sys_prompt,
                model=model or DEFAULT_FAST_MODEL,
                tool_permissions={"safe": True} # Give it basic tools by default
            )
            db.add(new_agent)
            await db.commit()
            
            # Now spawn the agent
            spawn_res = await self.spawn_agent(
                agent_name=subagent_name,
                task=task,
                team_id=team_id,
                parent_coordinator_id=_agent_id
            )
            
        return f"Successfully hired subagent {subagent_name}. They are working asynchronously. You will receive a <task-notification> in your chat history when they finish. You may continue working on other things."


# Singleton
agent_tools = AgentTools()
