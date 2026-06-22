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
from typing import Optional
from sqlalchemy import select

from core.memory.database import async_session
from core.memory.models import Agent, Team
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
            team_uuid = uuid.UUID(team_id) if isinstance(team_id, str) else team_id
            stmt = select(Agent).where(Agent.team_id == team_uuid, Agent.name == agent_name)
            result = await db.execute(stmt)
            agent = result.scalar_one_or_none()

            if not agent:
                return f"Error: No agent named '{agent_name}' found in this team."

            # Resolve project_id
            team_stmt = select(Team).where(Team.id == team_uuid)
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
            fallback_model=agent.fallback_model,
            reasoning_effort=getattr(agent, "reasoning_effort", "none") or "none",
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
        # Local import to prevent circular dependency
        from core.chat.message_router import message_router

        # Route the message through the system to wake up any mentioned agents
        # (or the coordinator if appropriate), rather than just silently persisting it.
        # Note: We must look up the sender_name to pass it properly.
        sender_name = "Agent"
        async with async_session() as db:
            sender_stmt = select(Agent).where(Agent.id == uuid.UUID(sender_id) if isinstance(sender_id, str) else sender_id)
            sender_res = await db.execute(sender_stmt)
            sender_agent = sender_res.scalar_one_or_none()
            if sender_agent:
                sender_name = sender_agent.name

        # If a recipient_name is explicitly specified, prepend it as an @mention
        # to ensure the router correctly identifies and triggers the target agent.
        final_text = f"@{recipient_name} {text}" if recipient_name and f"@{recipient_name}" not in text else text

        await message_router.route_message(
            text=final_text,
            sender_id=sender_id,
            team_id=team_id,
            sender_name=sender_name,
            attachments=[]
        )

        return "Message sent and team members notified."

    async def hire_subagent(self, role: str, expertise: str, task: str, team_id: str, _agent_id: str, model: str = None) -> str:
        """
        Dynamically creates a new subagent row in the database and spawns its loop asynchronously.
        The subagent receives a full production-grade system prompt with planning lifecycle
        and the task-notification return protocol. The DB row is auto-deleted after completion.
        """
        task_id = str(uuid.uuid4())
        subagent_name = f"Sub-{role.replace(' ', '')}_{task_id[:4]}"

        # Full production-grade system prompt for the subagent
        sys_prompt = (
            f"You are {subagent_name}, a temporary specialist subagent hired for one specific task.\n"
            f"Role: {role}\n"
            f"Expertise: {expertise}\n\n"
            "Follow this process STRICTLY:\n"
            "1. UNDERSTAND: Restate the task in your own words. Identify exactly what output is expected.\n"
            "2. PLAN: Write 2-3 bullet points outlining your approach.\n"
            "3. EXECUTE: Use your available tools step by step to complete the task.\n"
            "4. SCORE: Evaluate your result against the original task requirements (e.g. 9/10).\n"
            "5. RETURN: End your final message with the task-notification block below.\n\n"
            "Your final response MUST end with:\n"
            f"<task-notification>\n"
            f"  <task_id>{task_id}</task_id>\n"
            f"  <agent>{subagent_name}</agent>\n"
            f"  <status>completed</status>\n"
            f"  <result>Your concise result summary here (max 500 words)</result>\n"
            f"</task-notification>\n\n"
            "IMPORTANT CONSTRAINTS:\n"
            "- You are temporary. Do NOT hire further subagents.\n"
            "- You have no shared context with the team chat — your task description is all you have.\n"
            "- When done, stop. Your coordinator will handle next steps.\n"
        )

        # Correct tool_permissions format — keys match the tool category names in tool_executor.py
        subagent_permissions = {
            "file_read": "allow",
            "file_write": "allow",
            "bash": "allow",
            "web": "allow",
            "code_analysis": "allow",
            "memory": "allow",
        }

        async with async_session() as db:
            team_uuid = uuid.UUID(team_id) if isinstance(team_id, str) else team_id

            new_agent = Agent(
                team_id=team_uuid,
                name=subagent_name,
                role=role,
                system_prompt=sys_prompt,
                model=model or DEFAULT_FAST_MODEL,
                tool_permissions=subagent_permissions,
            )
            db.add(new_agent)
            await db.commit()
            await db.refresh(new_agent)
            new_agent_id = str(new_agent.id)

            # Resolve project_id via Team
            from core.memory.models import Team
            team_res = await db.execute(select(Team).where(Team.id == team_uuid))
            team_obj = team_res.scalar_one_or_none()
            project_id = str(team_obj.project_id) if team_obj else ""

        from core.agent.react_agent import ReACTAgent

        react = ReACTAgent(
            agent_id=new_agent_id,
            team_id=team_id,
            project_id=project_id,
            name=subagent_name,
            role=role,
            model=model or DEFAULT_FAST_MODEL,
            system_prompt=sys_prompt,
            parent_coordinator_id=_agent_id,
            task_id=task_id,
        )

        async def _run_and_cleanup():
            async with async_session() as agent_db:
                try:
                    await react.run_loop(agent_db, task)
                finally:
                    # Auto-delete the subagent row so the team roster stays clean
                    try:
                        from sqlalchemy import delete as sa_delete
                        await agent_db.execute(
                            sa_delete(Agent).where(Agent.id == uuid.UUID(new_agent_id))
                        )
                        await agent_db.commit()
                    except Exception as del_err:
                        import logging
                        logging.getLogger("carole.agent_tools").warning(
                            "Could not auto-delete subagent %s: %s", subagent_name, del_err
                        )

        asyncio.create_task(_run_and_cleanup())

        return (
            f"Hired subagent '{subagent_name}' (task_id={task_id}). "
            f"They are working asynchronously. You will receive a <task-notification> when they finish."
        )


# Singleton
agent_tools = AgentTools()
