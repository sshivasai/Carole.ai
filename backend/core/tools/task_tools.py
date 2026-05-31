"""
# backend/core/tools/task_tools.py

Database-backed task management tools for the collaborative task board.
Agents can create, list, update, and assign tasks — enabling real-time
Kanban-style project tracking visible in both the chat and the UI.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import async_session
from core.memory.models import Task, Agent
from core.chat.event_bus import event_bus


class TaskTools:
    async def create_task(
        self, team_id: str, title: str, description: str = "",
        priority: str = "medium", assignee_name: str = None
    ) -> str:
        """Creates a task and optionally assigns it to an agent by name."""
        async with async_session() as db:
            assigned_agent_id = None
            if assignee_name:
                stmt = select(Agent).where(Agent.team_id == team_id, Agent.name == assignee_name)
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()
                if agent:
                    assigned_agent_id = agent.id

            task = Task(
                team_id=team_id,
                title=title,
                description=description,
                priority=priority,
                assigned_agent_id=assigned_agent_id,
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
                    "assigned_to": assignee_name or "unassigned",
                },
            })

            assigned_msg = f" (assigned to {assignee_name})" if assignee_name else ""
            return f"✓ Task created: '{title}'{assigned_msg} [priority: {priority}]"

    async def list_tasks(self, team_id: str, status_filter: str = None) -> str:
        """Lists tasks for the team, optionally filtered by status."""
        async with async_session() as db:
            stmt = select(Task).where(Task.team_id == team_id)
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

    async def update_task(self, task_id: str, status: str = None, notes: str = None) -> str:
        """Updates a task's status and/or adds notes."""
        async with async_session() as db:
            stmt = select(Task).where(Task.id == task_id)
            result = await db.execute(stmt)
            task = result.scalar_one_or_none()
            if not task:
                return f"Error: Task '{task_id}' not found."

            old_status = task.status
            if status:
                task.status = status
            if notes:
                task.description = (task.description or "") + f"\n[Update] {notes}"
            task.updated_at = datetime.utcnow()
            await db.commit()

            # Broadcast status change
            await event_bus.publish(f"team:{task.team_id}", {
                "type": "task_update",
                "action": "updated",
                "task": {
                    "id": str(task.id), "title": task.title,
                    "old_status": old_status, "new_status": task.status,
                    "priority": task.priority,
                },
            })

            return f"✓ Task '{task.title}' updated: {old_status} → {task.status}"


# Singleton
task_tools = TaskTools()
