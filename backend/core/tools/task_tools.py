"""
# backend/core/tools/task_tools.py

Database-backed task management tools for the collaborative task board.
Agents can create, list, update, assign, and comment on tasks — enabling
real-time Kanban-style project tracking visible in both the chat and the UI.
"""

import uuid
import logging
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy import select

from core.memory.database import async_session
from core.memory.models import Task, Agent, TaskComment
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
        blocked_by_task_id: str = None, creator_agent_name: str = None,
        target_files: Optional[List[str]] = None,
        contract_spec: Optional[str] = None,
        verification_command: Optional[str] = None
    ) -> str:
        """Creates a task and optionally assigns it to an agent by name."""
        # Structured Task Specification (MetaGPT SOP Pattern)
        spec_parts = []
        if target_files:
            files_str = ", ".join([f"`{f}`" for f in target_files])
            spec_parts.append(f"**Target Files**: {files_str}")
        if contract_spec:
            spec_parts.append(f"**Contract / Interfaces**: {contract_spec}")
        if verification_command:
            spec_parts.append(f"**Verification**: `{verification_command}`")

        if spec_parts:
            spec_block = "\n\n### Task Specification:\n" + "\n".join(f"- {p}" for p in spec_parts)
            description = ((description or "").strip() + spec_block).strip()

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

            # If assigned, wake the agent via chat @mention (suppress if assigned to oneself)
            is_self_assignment = (
                assignee_agent is not None
                and creator_agent_name is not None
                and assignee_agent.name.strip().lower() == creator_agent_name.strip().lower()
            )
            if assignee_agent and not is_self_assignment:
                from core.chat.message_router import message_router
                if blocked_by_task_id:
                    assign_text = f"[TASK_ASSIGN] @{assignee_agent.name} task '{title}' (Task ID: {task.id}) has been assigned to you. However, it is currently BLOCKED by another task. You will be notified when it is unblocked. Do not start work yet. DO NOT create a new task — this task already exists on the board."
                else:
                    assign_text = f"[TASK_ASSIGN] @{assignee_agent.name} task '{title}' (Task ID: {task.id}) has been assigned to you. IMPORTANT: DO NOT use create_task — this task already exists on the board. Use update_task(task_id='{task.id}', status='in_progress') to start, then update_task(task_id='{task.id}', status='done') when finished."
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
            task.updated_at = datetime.now(timezone.utc)

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

            # Broadcast a visible chat message so the team knows (plain name, not @mention to prevent self-wakeup)
            from core.chat.message_router import message_router
            updater = f" by {agent_name}" if agent_name else ""
            chat_text = f"[TASK_UPDATE] Task '{task.title}' moved to '{task.status}'{updater}"
            await message_router.route_message(
                text=chat_text,
                sender_id="system",
                team_id=team_id_str,
                sender_name="System",
                attachments=[]
            )

            # If a new assignee was set, wake them via @mention (suppress if assigned to oneself)
            is_self_update = (
                new_assignee_agent is not None
                and agent_name is not None
                and new_assignee_agent.name.strip().lower() == agent_name.strip().lower()
            )
            if new_assignee_agent and not is_self_update:
                if task.blocked_by_task_id:
                    assign_text = f"[TASK_ASSIGN] @{new_assignee_agent.name} task '{task.title}' (Task ID: {task.id}) has been assigned to you. However, it is currently BLOCKED by another task. You will be notified when it is unblocked. Do not start work yet. DO NOT create a new task — this task already exists on the board."
                else:
                    assign_text = f"[TASK_ASSIGN] @{new_assignee_agent.name} task '{task.title}' (Task ID: {task.id}) has been assigned to you. Description: {task.description or 'No description provided.'}. IMPORTANT: DO NOT use create_task — this task already exists on the board. Use update_task(task_id='{task.id}', status='in_progress') to start, then update_task(task_id='{task.id}', status='done') when finished."
                await message_router.route_message(
                    text=assign_text,
                    sender_id="system",
                    team_id=team_id_str,
                    sender_name="System",
                    attachments=[]
                )
                if not task.blocked_by_task_id:
                    await message_router._enqueue_agent(new_assignee_agent, assign_text, db)

            # UNBLOCK ENGINE: If this task is now 'done', unblock tasks waiting on it
            if task.status == "done":
                unblock_stmt = select(Task).where(Task.blocked_by_task_id == task.id)
                unblock_res = await db.execute(unblock_stmt)
                blocked_tasks = unblock_res.scalars().all()
                unblock_notifications = []
                for b_task in blocked_tasks:
                    b_task.blocked_by_task_id = None
                    b_task.updated_at = datetime.now(timezone.utc)
                    
                    if b_task.assigned_agent_id:
                        agent_res = await db.execute(select(Agent).where(Agent.id == b_task.assigned_agent_id))
                        b_agent = agent_res.scalar_one_or_none()
                        if b_agent:
                            unblock_text = f"[TASK_UNBLOCKED] @{b_agent.name} the task you were waiting on ('{task.title}') is done. You are now unblocked and can begin work on your task: '{b_task.title}'."
                            unblock_notifications.append((b_agent, unblock_text))

                orchestrator_notification = None
                if not blocked_tasks:
                    # Notify Orchestrator that task completed and no downstream tasks are waiting
                    from sqlalchemy import func
                    coord_stmt = select(Agent).where(
                        Agent.team_id == task.team_id,
                        func.lower(Agent.role).in_(["orchestrator", "coordinator"])
                    ).limit(1)
                    coord_res = await db.execute(coord_stmt)
                    orchestrator = coord_res.scalar_one_or_none()
                    if orchestrator and (not agent_name or orchestrator.name.lower() != agent_name.lower()):
                        done_text = (
                            f"[TASK_DONE] @{orchestrator.name} task '{task.title}' was marked 'done'"
                            f"{f' by {agent_name}' if agent_name else ''}. "
                            f"All blocking dependencies are resolved. Please review deliverables, "
                            f"coordinate QA/testing if needed, or deliver the final synthesis to the user."
                        )
                        orchestrator_notification = (orchestrator, done_text)

                # Commit all task updates first so SQLite write locks are released before message dispatch
                await db.commit()

                # Dispatch notifications after commit
                for b_agent, unblock_text in unblock_notifications:
                    await message_router.route_message(
                        text=unblock_text,
                        sender_id="system",
                        team_id=team_id_str,
                        sender_name="System",
                        attachments=[]
                    )
                    await message_router._enqueue_agent(b_agent, unblock_text, db)

                if orchestrator_notification:
                    orch, done_text = orchestrator_notification
                    await message_router.route_message(
                        text=done_text,
                        sender_id="system",
                        team_id=team_id_str,
                        sender_name="System",
                        attachments=[]
                    )
                    await message_router._enqueue_agent(orch, done_text, db)

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
            sys_text = f"[TASK_COMMENT] {author_name} on '{task.title}': {text}"
            
            import re
            # Implicit mentions for assignee if no explicit mention is in the text
            if task.assigned_agent_id and not re.search(r"@\w+", text):
                agent_res = await db.execute(select(Agent).where(Agent.id == task.assigned_agent_id))
                assignee_agent = agent_res.scalar_one_or_none()
                if assignee_agent and str(assignee_agent.id) != author_id:
                    sys_text += f"\n(Implicitly notifying assignee: @{assignee_agent.name})"

            await message_router.route_message(
                text=sys_text,
                sender_id="system",
                team_id=team_id_str,
                sender_name="System",
                attachments=[]
            )
            
            return f"✓ Comment added to task '{task.title}'"

    # ── Implementation Plan Tools ────────────────────────────────────────────────

    async def write_task_plan(
        self, task_id: str, plan_markdown: str, agent_id: str, team_id: str
    ) -> str:
        """Writes an implementation plan for a task to disk and the database.

        Creates (or overwrites) a Markdown plan file at:
            ~/.carole/workspaces/{project_slug}/.carole/{team_slug}/plans/{task_id}_plan.md

        Sets plan_status to 'awaiting_approval' if the agent does NOT have
        auto_approve_plans enabled, or directly to 'approved' if it does.
        """
        async with async_session() as db:
            task = await _resolve_task(db, task_id, team_id)
            if not task:
                return f"Error: Task '{task_id}' not found."

            # Resolve the agent's auto_approve_plans setting
            auto_approve = False
            try:
                agent_uuid = uuid.UUID(agent_id)
                agent_rec = (await db.execute(
                    select(Agent).where(Agent.id == agent_uuid)
                )).scalar_one_or_none()
                if agent_rec:
                    auto_approve = bool(agent_rec.auto_approve_plans)
            except Exception:
                pass

            # Resolve plan file path via FileTools (handles project/team slug resolution)
            try:
                from core.tools.file_tools import file_tools
                carole_dir = await file_tools.get_team_carole_dir(team_id, db=db)
                plans_dir = carole_dir / "plans"
                plans_dir.mkdir(parents=True, exist_ok=True)
                plan_path = plans_dir / f"{str(task.id)}_plan.md"
                plan_path.write_text(plan_markdown, encoding="utf-8")
                plan_file_path_str = str(plan_path)
            except Exception as e:
                logger.warning("Could not write plan file for task %s: %s", task_id, e)
                plan_file_path_str = None

            # Persist to DB
            task.implementation_plan = plan_markdown
            task.plan_file_path = plan_file_path_str
            task.plan_status = "approved" if auto_approve else "awaiting_approval"
            task.plan_feedback = None  # clear old feedback
            await db.commit()

            # Broadcast update
            team_id_str = str(task.team_id)
            await event_bus.publish(f"team:{team_id_str}", {
                "type": "task_update",
                "action": "plan_created",
                "task": {
                    "id": str(task.id),
                    "title": task.title,
                    "plan_status": task.plan_status,
                }
            })

            if auto_approve:
                return (
                    f"✓ Implementation plan written for task '{task.title}' and auto-approved.\n"
                    f"Plan saved to: {plan_file_path_str or '(DB only)'}\n"
                    f"You may now create the todo list and begin execution."
                )
            else:
                return (
                    f"✓ Implementation plan written for task '{task.title}'.\n"
                    f"Plan saved to: {plan_file_path_str or '(DB only)'}\n"
                    f"Status: awaiting admin approval. Do NOT begin work until the plan is approved."
                )

    async def request_plan_approval(self, task_id: str, team_id: str) -> str:
        """Re-submits a plan for approval after the agent has revised it.

        Use this after addressing inline review comments or requested changes.
        Transitions plan_status from 'revision_requested' back to 'awaiting_approval'.
        """
        async with async_session() as db:
            task = await _resolve_task(db, task_id, team_id)
            if not task:
                return f"Error: Task '{task_id}' not found."

            if not task.implementation_plan:
                return f"Error: Task '{task.title}' has no implementation plan. Use write_task_plan first."

            task.plan_status = "awaiting_approval"
            await db.commit()

            team_id_str = str(task.team_id)
            await event_bus.publish(f"team:{team_id_str}", {
                "type": "task_update",
                "action": "plan_resubmitted",
                "task": {
                    "id": str(task.id),
                    "title": task.title,
                    "plan_status": task.plan_status,
                }
            })
            return f"✓ Implementation plan for '{task.title}' re-submitted for approval."

    async def update_task_todos(
        self, task_id: str, team_id: str,
        todos: list = None,
        toggle_id: str = None
    ) -> str:
        """Creates or updates the todo checklist for a task.

        Args:
            task_id: Task ID (UUID, prefix, or title).
            team_id: Team ID string.
            todos: Full list of todo items to set. Each item is a dict with keys:
                   'id' (str), 'text' (str), 'done' (bool).
                   If provided, REPLACES the full todo_list.
            toggle_id: If provided, toggles the 'done' status of the todo item
                       with this id. Takes precedence over a full todos list.

        Examples:
            # Set a new todo list
            update_task_todos(task_id, team_id, todos=[
                {"id": "t1", "text": "Update database schema", "done": false},
                {"id": "t2", "text": "Write API endpoint", "done": false},
            ])
            # Toggle a single item
            update_task_todos(task_id, team_id, toggle_id="t1")
        """
        async with async_session() as db:
            task = await _resolve_task(db, task_id, team_id)
            if not task:
                return f"Error: Task '{task_id}' not found."

            current = list(task.todo_list or [])

            if toggle_id:
                # Toggle a single item's done state
                found = False
                for item in current:
                    if item.get("id") == toggle_id:
                        item["done"] = not item.get("done", False)
                        found = True
                        break
                if not found:
                    return f"Error: Todo item '{toggle_id}' not found in task '{task.title}'."
                task.todo_list = current
            elif todos is not None:
                # Validate and set full list
                validated = []
                for item in todos:
                    if not isinstance(item, dict) or "text" not in item:
                        return "Error: Each todo item must be a dict with at least a 'text' key."
                    validated.append({
                        "id": item.get("id", str(uuid.uuid4())[:8]),
                        "text": str(item["text"]),
                        "done": bool(item.get("done", False)),
                    })
                task.todo_list = validated
            else:
                return "Error: Provide either 'todos' list or a 'toggle_id' to update."

            await db.commit()

            done_count = sum(1 for i in (task.todo_list or []) if i.get("done"))
            total = len(task.todo_list or [])

            # Broadcast so Kanban card live-updates
            team_id_str = str(task.team_id)
            await event_bus.publish(f"team:{team_id_str}", {
                "type": "task_update",
                "action": "todos_updated",
                "task": {
                    "id": str(task.id),
                    "title": task.title,
                    "todo_list": task.todo_list,
                }
            })
            return f"✓ Todos updated for '{task.title}': {done_count}/{total} done."


# Singleton
task_tools = TaskTools()
