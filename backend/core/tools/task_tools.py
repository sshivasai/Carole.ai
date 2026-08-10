"""
# backend/core/tools/task_tools.py

Database-backed task management tools for the collaborative task board.
Agents can create, list, update, assign, and comment on tasks — enabling
real-time Kanban-style project tracking visible in both the chat and the UI.
"""

import uuid
import logging
from datetime import datetime
from sqlalchemy import select

from core.memory.database import async_session
from core.memory.models import Task, Agent
from core.chat.event_bus import event_bus

logger = logging.getLogger("carole.task_tools")


async def _resolve_task(db, task_id_input: str, team_id_str: str = None) -> Task | None:
    """Finds a task by full UUID, short UUID prefix, exact title, or fuzzy title match."""
    if not task_id_input:
        return None

    task_id_str = str(task_id_input).strip()

    # 1. Try full UUID
    try:
        task_uuid = uuid.UUID(task_id_str)
        stmt = select(Task).where(Task.id == task_uuid)
        res = await db.execute(stmt)
        task = res.scalar_one_or_none()
        if task:
            return task
    except (ValueError, AttributeError):
        pass

    # Fetch tasks for team to check prefix or title
    stmt = select(Task)
    if team_id_str:
        try:
            stmt = stmt.where(Task.team_id == uuid.UUID(team_id_str))
        except (ValueError, AttributeError):
            pass
    res = await db.execute(stmt)
    all_tasks = res.scalars().all()

    # 2a. Short ID prefix match
    for t in all_tasks:
        if str(t.id).lower().startswith(task_id_str.lower()):
            return t

    # 2b. Exact title match
    for t in all_tasks:
        if t.title.strip().lower() == task_id_str.lower():
            return t

    # 2c. Substring title match
    for t in all_tasks:
        if task_id_str.lower() in t.title.strip().lower():
            return t

    return None


class TaskTools:
    async def create_task(
        self, team_id: str, title: str, description: str = "",
        priority: str = "medium", assignee_name: str = None,
        blocked_by_task_id: str = None
    ) -> str:
        """Creates a task and optionally assigns it to an agent by name."""
        async with async_session() as db:
            assigned_agent_id = None
            assignee_agent = None
            if assignee_name:
                stmt = select(Agent).where(
                    Agent.team_id == uuid.UUID(team_id),
                    Agent.name == assignee_name
                )
                result = await db.execute(stmt)
                assignee_agent = result.scalar_one_or_none()
                if assignee_agent:
                    assigned_agent_id = assignee_agent.id

            task = Task(
                team_id=uuid.UUID(team_id),
                title=title,
                description=description,
                priority=priority,
                assigned_agent_id=assigned_agent_id,
                blocked_by_task_id=uuid.UUID(blocked_by_task_id) if blocked_by_task_id else None,
                created_by="agent",
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)

            # Broadcast task creation to the UI
            await event_bus.publish(f"team:{team_id}", {
                "type": "task_update",
                "action": "created",
                "task": {
                    "id": str(task.id), "title": title, "description": description,
                    "status": "todo", "priority": priority,
                    "assigned_agent_id": str(assigned_agent_id) if assigned_agent_id else None,
                },
            })

            # If assigned, wake the agent via chat @mention
            if assignee_agent:
                from core.chat.message_router import message_router
                if blocked_by_task_id:
                    assign_text = f"[TASK_ASSIGN] @{assignee_agent.name} a new task '{title}' (ID: {task.id}) has been assigned to you. However, it is currently BLOCKED by another task. You will be notified when it is unblocked. Do not start work yet."
                else:
                    assign_text = f"[TASK_ASSIGN] @{assignee_agent.name} a new task '{title}' (ID: {task.id}) has been assigned to you. Please start working on it. Update the task status to 'in_progress' when starting and 'done' when finished."
                await message_router.route_message(
                    text=assign_text,
                    sender_id="system",
                    team_id=team_id,
                    sender_name="System",
                    attachments=[]
                )

            assigned_msg = f" (assigned to {assignee_name})" if assignee_name else ""
            return f"✓ Task created: '{title}' (ID: {task.id}){assigned_msg} [priority: {priority}]"

    async def list_tasks(self, team_id: str, status_filter: str = None) -> str:
        """Lists tasks for the team, optionally filtered by status."""
        async with async_session() as db:
            stmt = select(Task).where(Task.team_id == uuid.UUID(team_id))
            if status_filter:
                stmt = stmt.where(Task.status == status_filter)
            stmt = stmt.order_by(Task.created_at.desc())
            result = await db.execute(stmt)
            tasks = result.scalars().all()

            if not tasks:
                return "No tasks found."

            lines = [f"📋 Tasks ({len(tasks)} total):"]
            for t in tasks:
                assignee = ""
                if t.assigned_agent_id:
                    agent_stmt = select(Agent).where(Agent.id == t.assigned_agent_id)
                    agent_result = await db.execute(agent_stmt)
                    agent = agent_result.scalar_one_or_none()
                    assignee = f" → {agent.name}" if agent else ""

                status_icons = {
                    "todo": "⬜", "in_progress": "🔵", "review": "🟡",
                    "done": "✅", "blocked": "🔴",
                }
                icon = status_icons.get(t.status, "⬜")
                lines.append(f"  {icon} [{t.priority}] {t.title}{assignee} (id: {str(t.id)[:8]})")

            return "\n".join(lines)

    async def update_task(
        self, task_id: str, status: str = None, notes: str = None,
        assignee_name: str = None, agent_name: str = None,
        blocked_by_task_id: str = None
    ) -> str:
        """Updates a task's status, notes, and/or assignee. Wakes the agent on assignment."""
        async with async_session() as db:
            task = await _resolve_task(db, task_id)
            if not task:
                return f"Error: Task '{task_id}' not found."

            old_status = task.status
            if status:
                valid_statuses = {"todo", "in_progress", "review", "done", "blocked"}
                if status not in valid_statuses:
                    return f"Error: Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}"
                task.status = status
            if notes:
                from core.memory.models import TaskComment
                comment = TaskComment(
                    task_id=task.id,
                    author_id="system",
                    author_name=agent_name or "System",
                    text=notes
                )
                db.add(comment)
            if blocked_by_task_id is not None:
                try:
                    task.blocked_by_task_id = uuid.UUID(blocked_by_task_id) if blocked_by_task_id else None
                except (ValueError, AttributeError):
                    return f"Error: Invalid blocked_by_task_id format."
            task.updated_at = datetime.utcnow()

            # Handle assignee change
            new_assignee_agent = None
            if assignee_name:
                a_stmt = select(Agent).where(
                    Agent.team_id == task.team_id,
                    Agent.name == assignee_name
                )
                a_res = await db.execute(a_stmt)
                new_assignee_agent = a_res.scalar_one_or_none()
                if new_assignee_agent:
                    task.assigned_agent_id = new_assignee_agent.id
                else:
                    return f"Error: No agent named '{assignee_name}' found in this team."

            await db.commit()

            # Broadcast status change to UI with complete status field
            team_id_str = str(task.team_id)
            await event_bus.publish(f"team:{team_id_str}", {
                "type": "task_update",
                "action": "updated",
                "task": {
                    "id": str(task.id),
                    "title": task.title,
                    "status": task.status,
                    "old_status": old_status,
                    "new_status": task.status,
                    "priority": task.priority,
                    "description": task.description,
                    "assigned_agent_id": str(task.assigned_agent_id) if task.assigned_agent_id else None,
                },
            })

            # Broadcast a visible chat message so the team knows
            from core.chat.message_router import message_router
            updater = f" by @{agent_name}" if agent_name else ""
            chat_text = f"[TASK_UPDATE] Task '{task.title}' moved to '{task.status}'{updater}"
            await message_router.route_message(
                text=chat_text,
                sender_id="system",
                team_id=team_id_str,
                sender_name="System",
                attachments=[]
            )

            # If a new assignee was set, wake them via @mention
            if new_assignee_agent:
                if task.blocked_by_task_id:
                    assign_text = f"[TASK_ASSIGN] @{new_assignee_agent.name} task '{task.title}' (ID: {task.id}) has been assigned to you. However, it is currently BLOCKED by another task. You will be notified when it is unblocked. Do not start work yet."
                else:
                    assign_text = f"[TASK_ASSIGN] @{new_assignee_agent.name} task '{task.title}' (ID: {task.id}) has been assigned to you. Please start working on it. Update task status to 'in_progress' when starting and 'done' when finished."
                await message_router.route_message(
                    text=assign_text,
                    sender_id="system",
                    team_id=team_id_str,
                    sender_name="System",
                    attachments=[]
                )

            # UNBLOCK ENGINE: If this task is now 'done', unblock tasks waiting on it
            if task.status == "done":
                unblock_stmt = select(Task).where(Task.blocked_by_task_id == task.id)
                unblock_res = await db.execute(unblock_stmt)
                blocked_tasks = unblock_res.scalars().all()
                for b_task in blocked_tasks:
                    b_task.blocked_by_task_id = None
                    b_task.updated_at = datetime.utcnow()
                    
                    if b_task.assigned_agent_id:
                        agent_res = await db.execute(select(Agent).where(Agent.id == b_task.assigned_agent_id))
                        b_agent = agent_res.scalar_one_or_none()
                        if b_agent:
                            await message_router.route_message(
                                text=f"[TASK_UNBLOCKED] @{b_agent.name} the task you were waiting on ('{task.title}') is done. You are now unblocked and can begin work on your task: '{b_task.title}'.",
                                sender_id="system",
                                team_id=team_id_str,
                                sender_name="System",
                                attachments=[]
                            )
                if blocked_tasks:
                    await db.commit()

            summary = f"✓ Task '{task.title}' updated: {old_status} → {task.status}"
            if new_assignee_agent:
                summary += f" | assigned to {new_assignee_agent.name}"
            return summary

    async def comment_on_task(self, task_id: str, text: str, author_id: str, author_name: str) -> str:
        """Adds a comment to a task and broadcasts a chat notification."""
        async with async_session() as db:
            from core.memory.models import TaskComment
            task = await _resolve_task(db, task_id)
            if not task:
                return f"Error: Task '{task_id}' not found."
                
            comment = TaskComment(
                task_id=task.id,
                author_id=author_id,
                author_name=author_name,
                text=text
            )
            db.add(comment)
            await db.commit()
            
            # Broadcast UI update + visible chat message
            team_id_str = str(task.team_id)
            await event_bus.publish(f"team:{team_id_str}", {
                "type": "task_update",
                "action": "updated",
                "task": {
                    "id": str(task.id),
                    "title": task.title,
                    "status": task.status,
                    "description": task.description,
                    "assigned_agent_id": str(task.assigned_agent_id) if task.assigned_agent_id else None,
                }
            })

            from core.chat.message_router import message_router
            await message_router.route_message(
                text=f"[TASK_COMMENT] @{author_name} commented on '{task.title}': {text[:200]}",
                sender_id="system",
                team_id=team_id_str,
                sender_name="System",
                attachments=[]
            )
            
            return f"✓ Comment added to task '{task.title}'"

# Singleton
task_tools = TaskTools()
