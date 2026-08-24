"""
# backend/core/tools/agent_tools.py

Tools for inter-agent delegation and coordination.

- spawn_agent: Creates a new ReACT loop for a named agent in the same team.
  Now supports parent_coordinator_id and auto-generated task_id for the
  <task-notification> protocol.
- send_message: Publishes a message to the team EventBus, optionally targeting a specific agent.
"""

import re
import uuid
import asyncio
import logging
from typing import Optional
from sqlalchemy import select, func, delete

from core.memory.database import async_session
from core.memory.models import Agent, Team
from core.config import DEFAULT_FAST_MODEL
from core.prompts import get_prompt

logger = logging.getLogger("carole.agent_tools")

# Strong references to background subagent tasks so they aren't garbage-collected
# mid-run (asyncio only holds weak refs to tasks created via asyncio.create_task).
_running_subagent_tasks: set = set()


async def _publish_failure_notification(
    task_id: str,
    parent_coordinator_id: Optional[str],
    team_id: str,
    agent_name: str,
    exc: BaseException,
) -> None:
    """Publish a failure <task-notification> to the parent coordinator's team topic.

    Mirrors the success-path event structure used in ReACTAgent.run_loop
    (see backend/core/agent/react_agent.py:625-634): a "message" event with
    `is_task_notification=True` published to the `team:{team_id}` topic, with the
    notification XML carried in the "text" field.
    """
    try:
        from core.chat.event_bus import event_bus
        notification = (
            f"<task-notification>\n"
            f"  <task_id>{task_id}</task_id>\n"
            f"  <agent>{agent_name}</agent>\n"
            f"  <status>failed</status>\n"
            f"  <result>Subagent '{agent_name}' crashed: "
            f"{type(exc).__name__}: {exc}</result>\n"
            f"</task-notification>"
        )
        await event_bus.publish(f"team:{team_id}", {
            "type": "message",
            "sender_id": agent_name,
            "sender_name": agent_name,
            "role": "subagent",
            "text": notification,
            "is_task_notification": True,
        })
    except Exception:
        logger.exception(
            "Failed to publish failure task-notification for subagent %s (task_id=%s)",
            agent_name, task_id,
        )


def _make_done_callback(
    task_id: str,
    parent_coordinator_id: Optional[str],
    team_id: str,
    agent_name: str,
):
    """Build a done_callback for a subagent asyncio.Task.

    On exception, publishes a failure <task-notification> to the parent
    coordinator so it doesn't hang forever waiting for a result. Also discards
    the task from the strong-reference set so it can be GC'd once finished.
    """
    def _cb(t: asyncio.Task) -> None:
        _running_subagent_tasks.discard(t)
        if parent_coordinator_id is None:
            return
        try:
            exc = t.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            coro = _publish_failure_notification(
                task_id, parent_coordinator_id, team_id, agent_name, exc
            )
            # Use get_running_loop() — get_event_loop() is deprecated in 3.10+
            # and raises RuntimeError during shutdown when no loop is running.
            try:
                loop = asyncio.get_running_loop()
                asyncio.ensure_future(coro, loop=loop)
            except RuntimeError:
                # No running event loop (e.g. shutdown) — log and skip.
                logger.warning(
                    "[done_callback] No running event loop for failure notification "
                    "(subagent=%s task_id=%s). Skipping.",
                    agent_name, task_id,
                )
    return _cb


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
            try:
                async with async_session() as agent_db:
                    await react.run_loop(agent_db, task)
            except Exception as e:
                logger.exception(
                    "[spawn_agent] Subagent %s crashed: %s", agent.name, e
                )

        # NOTE (Bug 3 race): There is an inherent TOCTOU race here — the
        # subagent may emit its success <task-notification> before the parent
        # coordinator has subscribed to the team topic. The EventBus keeps a
        # per-topic history buffer (last 100 events) which is replayed to
        # late-joining subscribers (see backend/core/chat/event_bus.py:47-54),
        # so in practice the parent will still receive the notification on
        # subscribe via replay. The done_callback below additionally covers the
        # failure case so the parent never hangs on a crash.
        _task = asyncio.create_task(_run())
        _running_subagent_tasks.add(_task)
        _task.add_done_callback(
            _make_done_callback(task_id, parent_coordinator_id, str(agent.team_id), agent.name)
        )

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

    async def create_team_agent(
        self,
        name: str,
        role: str,
        expertise: str = "",
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        personality: Optional[str] = None,
        team_id: str = "",
        _agent_id: str = "",
    ) -> str:
        """
        Permanently adds a new AI agent / teammate to the team.
        Unlike hire_subagent, this agent is NOT auto-deleted and remains a full,
        permanent member of the team roster in the UI and database.
        """
        clean_name = re.sub(r'[^a-zA-Z0-9_-]+', '', name.strip().lstrip('@'))
        if not clean_name:
            clean_name = f"Agent_{uuid.uuid4().hex[:4]}"

        from core.prompts import build_agent_system_prompt
        base_prompt = system_prompt or build_agent_system_prompt(name=clean_name, role=role, personality=personality or "professional")

        if expertise:
            base_prompt += f"\n\nSPECIALIZATION & EXPERTISE:\n{expertise}\n"

        team_uuid = uuid.UUID(team_id) if isinstance(team_id, str) else team_id

        async with async_session() as db:
            # Check for name collision in the same team
            stmt = select(Agent).where(Agent.team_id == team_uuid, Agent.name == clean_name)
            existing = (await db.execute(stmt)).scalar_one_or_none()
            if existing:
                return f"Teammate '@{clean_name}' already exists on the team roster ({existing.role}). If you wish to update their profile or skills, use update_team_agent."

            # Extract skills list from expertise or role
            extracted_skills = []
            if expertise:
                extracted_skills = [s.strip() for s in re.split(r'[,;]|\band\b', expertise) if s.strip() and len(s.strip()) > 1]
            elif role:
                extracted_skills = [role]

            new_agent = Agent(
                team_id=team_uuid,
                name=clean_name,
                role=role,
                system_prompt=base_prompt,
                model=model or DEFAULT_FAST_MODEL,
                personality=personality or "professional",
                skills=extracted_skills,
                tool_permissions={
                    "file_read": "allow",
                    "file_write": "allow",
                    "bash": "allow",
                    "web": "allow",
                    "code_analysis": "allow",
                    "memory": "allow",
                    "interaction": "allow",
                    "subagents": "allow",
                },
            )
            db.add(new_agent)
            await db.commit()
            await db.refresh(new_agent)

            # Broadcast agent_created event for real-time UI synchronization
            from core.chat.event_bus import event_bus
            agent_payload = {
                "id": str(new_agent.id),
                "name": new_agent.name,
                "role": new_agent.role,
                "model": new_agent.model,
                "fallback_model": new_agent.fallback_model,
                "reasoning_effort": new_agent.reasoning_effort or "none",
                "team_id": str(new_agent.team_id),
                "personality": new_agent.personality,
                "skills": new_agent.skills or [],
                "custom_instructions": new_agent.custom_instructions,
            }
            await event_bus.publish(f"team:{team_id}", {
                "type": "agent_created",
                "agent": agent_payload,
            })

            # Broadcast team message announcing the new member
            from core.chat.message_router import message_router
            await message_router.route_message(
                text=f"[AGENT_ADD] New agent @{new_agent.name} ({new_agent.role}) joined the team!",
                sender_id="system",
                team_id=str(team_id),
                sender_name="System",
                attachments=[],
            )

        return f"Successfully added permanent teammate '@{clean_name}' ({role}) to the team. They are now on the team roster and can be @mentioned directly."

    async def update_team_agent(
        self,
        name_or_id: str,
        new_name: Optional[str] = None,
        role: Optional[str] = None,
        expertise: Optional[str] = None,
        model: Optional[str] = None,
        personality: Optional[str] = None,
        custom_instructions: Optional[str] = None,
        team_id: str = "",
        _agent_id: str = "",
    ) -> str:
        """
        Updates an existing permanent teammate's profile, role, expertise, model, or instructions.
        """
        team_uuid = uuid.UUID(team_id) if isinstance(team_id, str) else team_id
        target = name_or_id.strip().lstrip('@')

        async with async_session() as db:
            agent = None
            try:
                agent_uuid = uuid.UUID(target)
                stmt = select(Agent).where(Agent.team_id == team_uuid, Agent.id == agent_uuid)
                agent = (await db.execute(stmt)).scalar_one_or_none()
            except ValueError:
                pass

            if not agent:
                stmt = select(Agent).where(Agent.team_id == team_uuid, func.lower(Agent.name) == target.lower())
                agent = (await db.execute(stmt)).scalar_one_or_none()

            if not agent:
                return f"Error: Could not find agent '{name_or_id}' in the current team roster."

            changes = []
            if new_name:
                clean_new_name = re.sub(r'[^a-zA-Z0-9_-]+', '', new_name.strip().lstrip('@'))
                if clean_new_name and clean_new_name != agent.name:
                    changes.append(f"name changed from @{agent.name} to @{clean_new_name}")
                    agent.name = clean_new_name

            if role and role != agent.role:
                changes.append(f"role updated to '{role}'")
                agent.role = role

            if model and model != agent.model:
                changes.append(f"model changed to '{model}'")
                agent.model = model

            if personality and personality != agent.personality:
                changes.append(f"personality set to '{personality}'")
                agent.personality = personality

            if custom_instructions is not None:
                agent.custom_instructions = custom_instructions
                changes.append("custom instructions updated")

            if expertise:
                changes.append(f"expertise updated: {expertise}")
                agent.skills = [s.strip() for s in re.split(r'[,;]|\band\b', expertise) if s.strip() and len(s.strip()) > 1]
            elif role and not agent.skills:
                agent.skills = [role]

            # Rebuild prompt if relevant fields changed
            if role or new_name or personality or expertise or custom_instructions:
                from core.prompts import build_agent_system_prompt
                base_prompt = build_agent_system_prompt(name=agent.name, role=agent.role, personality=agent.personality or "professional")
                if expertise:
                    base_prompt += f"\n\nSPECIALIZATION & EXPERTISE:\n{expertise}\n"
                elif agent.custom_instructions:
                    base_prompt += f"\n\nSPECIAL CUSTOM INSTRUCTIONS:\n{agent.custom_instructions}\n"
                agent.system_prompt = base_prompt

            await db.commit()
            await db.refresh(agent)

            # Broadcast agent_updated event for real-time UI synchronization
            from core.chat.event_bus import event_bus
            agent_payload = {
                "id": str(agent.id),
                "name": agent.name,
                "role": agent.role,
                "model": agent.model,
                "fallback_model": agent.fallback_model,
                "reasoning_effort": agent.reasoning_effort or "none",
                "team_id": str(agent.team_id),
                "personality": agent.personality,
                "skills": agent.skills or [],
                "custom_instructions": agent.custom_instructions,
            }
            await event_bus.publish(f"team:{team_id}", {
                "type": "agent_updated",
                "agent": agent_payload,
            })

            # Broadcast team message
            from core.chat.message_router import message_router
            changes_desc = ", ".join(changes) if changes else "configuration refreshed"
            await message_router.route_message(
                text=f"[AGENT_UPDATE] @{agent.name}'s profile was updated: {changes_desc}",
                sender_id="system",
                team_id=str(team_id),
                sender_name="System",
                attachments=[],
            )

            return f"Successfully updated teammate '@{agent.name}': {changes_desc}."

    async def delete_team_agent(
        self,
        name_or_id: str,
        team_id: str = "",
        _agent_id: str = "",
    ) -> str:
        """
        Permanently removes an agent/teammate from the team.
        """
        team_uuid = uuid.UUID(team_id) if isinstance(team_id, str) else team_id
        target = name_or_id.strip().lstrip('@')

        # Safety check: Protect coordinator / Archer
        if target.lower() in ("archer", "coordinator", "orchestrator"):
            return "Error: Cannot delete the team Coordinator / Archer."

        async with async_session() as db:
            agent = None
            try:
                agent_uuid = uuid.UUID(target)
                stmt = select(Agent).where(Agent.team_id == team_uuid, Agent.id == agent_uuid)
                agent = (await db.execute(stmt)).scalar_one_or_none()
            except ValueError:
                pass

            if not agent:
                stmt = select(Agent).where(Agent.team_id == team_uuid, func.lower(Agent.name) == target.lower())
                agent = (await db.execute(stmt)).scalar_one_or_none()

            if not agent:
                return f"Error: Could not find agent '{name_or_id}' in the current team roster."

            if agent.name.lower() in ("archer", "coordinator") or "orchestrator" in agent.role.lower():
                return "Error: Cannot delete the team Coordinator."

            deleted_name = agent.name
            deleted_role = agent.role
            deleted_id = str(agent.id)

            await db.delete(agent)
            await db.commit()

            # Broadcast agent_deleted event
            from core.chat.event_bus import event_bus
            await event_bus.publish(f"team:{team_id}", {
                "type": "agent_deleted",
                "agent_id": deleted_id,
            })

            # Broadcast team chat message
            from core.chat.message_router import message_router
            await message_router.route_message(
                text=f"[AGENT_REMOVE] @{deleted_name} ({deleted_role}) has been removed from the team.",
                sender_id="system",
                team_id=str(team_id),
                sender_name="System",
                attachments=[],
            )

            return f"Successfully removed '@{deleted_name}' ({deleted_role}) from the team roster."

    async def hire_subagent(self, role: str, expertise: str, task: str, team_id: str, _agent_id: str, model: str = None) -> str:
        """
        Dynamically creates a new subagent row in the database and spawns its loop asynchronously.
        The subagent receives a full production-grade system prompt with planning lifecycle
        and the task-notification return protocol. The DB row is auto-deleted after completion.
        """
        task_id = str(uuid.uuid4())
        subagent_name = f"Sub-{role.replace(' ', '')}_{task_id[:4]}"

        from core.prompts import build_agent_system_prompt
        base_prompt = build_agent_system_prompt(name=subagent_name, role=role, personality="subagent")

        sys_prompt = (
            f"{base_prompt}\n\n"
            f"SPECIALIZATION & SCOPE:\nRole: {role} | Expertise: {expertise}\n\n"
            f"SUBAGENT COMPLETION PROTOCOL:\n"
            "You were hired for this specific task. Execute the necessary actions (e.g. write_file, execute_command, etc.) using [ACTION]tool_name(...) tags.\n"
            "When the task is complete, your final response MUST end with:\n"
            f"<task-notification>\n"
            f"  <task_id>{task_id}</task_id>\n"
            f"  <agent>{subagent_name}</agent>\n"
            f"  <status>completed</status>\n"
            f"  <result>Your concise result summary here (max 500 words)</result>\n"
            f"</task-notification>\n"
        )

        # Correct tool_permissions format — keys match the tool category names in tool_executor.py
        # NOTE: "subagents" is explicitly blocked so hired subagents can never
        # call hire_subagent / spawn_agent / send_message. This is enforced at
        # the AccessControl gate before any tool code runs, making the depth
        # guard in _wrap_hire_subagent a belt-and-suspenders fallback only.
        subagent_permissions = {
            "file_read": "allow",
            "file_write": "allow",
            "bash": "allow",
            "web": "allow",
            "code_analysis": "allow",
            "memory": "allow",
            "interaction": "allow",
            "subagents": "block",  # Subagents CANNOT hire or spawn further agents
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

            # Resolve project_id via Team (Team is imported at module top)
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
            # Mirror spawn_agent: pass through reasoning_effort and fallback_model
            # so the subagent uses the same model-behavior configuration as the
            # agent that hired it. (Bug 4 fix.)
            fallback_model=getattr(new_agent, "fallback_model", None),
            reasoning_effort=getattr(new_agent, "reasoning_effort", "none") or "none",
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

        # NOTE (Bug 3 race): As with spawn_agent, a very fast subagent could
        # emit its success <task-notification> before the parent coordinator
        # subscribes to the team topic. The EventBus history-replay buffer
        # (backend/core/chat/event_bus.py:47-54) mitigates this for the success
        # case, and the done_callback below guarantees the parent is notified
        # on crash so it never hangs forever.
        _task = asyncio.create_task(_run_and_cleanup())
        _running_subagent_tasks.add(_task)
        _task.add_done_callback(
            _make_done_callback(task_id, _agent_id, str(team_id), subagent_name)
        )

        return (
            f"Hired subagent '{subagent_name}' (task_id={task_id}). "
            f"They are working asynchronously. You will receive a <task-notification> when they finish."
        )


# Singleton
agent_tools = AgentTools()
