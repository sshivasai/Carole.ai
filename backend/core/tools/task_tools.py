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
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import async_session
from core.memory.models import Task, Agent, TaskComment
from core.chat.event_bus import event_bus
from core.agent.workflow_dag import workflow_dag, DAGCycleError

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
        if team_id_str:
            try:
                stmt = stmt.where(Task.team_id == uuid.UUID(str(team_id_str)))
            except (ValueError, AttributeError):
                pass
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
        verification_command: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
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
            team_uuid = uuid.UUID(team_id) if isinstance(team_id, str) else team_id
            # Fetch existing tasks to check DAG acyclicity
            stmt_all = select(Task).where(Task.team_id == team_uuid)
            existing_tasks = (await db.execute(stmt_all)).scalars().all()

            # Clean and normalize dependencies
            clean_deps: List[str] = []
            if depends_on:
                for d in depends_on:
                    resolved_d = await _resolve_task(db, str(d), str(team_uuid))
                    dep_id = str(resolved_d.id) if resolved_d else str(d).strip().lower()
                    if dep_id and dep_id not in clean_deps:
                        clean_deps.append(dep_id)

            if blocked_by_task_id:
                resolved_b = await _resolve_task(db, str(blocked_by_task_id), str(team_uuid))
                b_id = str(resolved_b.id) if resolved_b else str(blocked_by_task_id).strip().lower()
                if b_id and b_id not in clean_deps:
                    clean_deps.append(b_id)

            known_ids = {str(existing.id).lower() for existing in existing_tasks}
            missing = [dependency for dependency in clean_deps if dependency not in known_ids]
            if missing:
                return f"Error: Unknown task dependencies: {', '.join(missing)}"

            if priority not in {"low", "medium", "high", "critical"}:
                return f"Error: Invalid priority '{priority}'."

            task_uuid = uuid.uuid4()
            task_uuid_str = str(task_uuid)

            # Validate DAG acyclicity
            try:
                workflow_dag.validate_acyclic(
                    tasks=existing_tasks,
                    new_or_updated_task_id=task_uuid_str,
                    new_dependencies=clean_deps,
                )
            except DAGCycleError as e:
                return f"Error: Cannot create task — {str(e)}"

            # Determine initial status based on dependencies
            initial_status = "todo"
            primary_blocked_by = None
            if clean_deps:
                # Check if any dependencies are not yet 'done'
                status_map = {str(t.id).lower(): t.status for t in existing_tasks}
                all_done = all(status_map.get(d) == "done" for d in clean_deps if d in status_map)
                if not all_done:
                    initial_status = "blocked"
                    try:
                        primary_blocked_by = uuid.UUID(clean_deps[0])
                    except (ValueError, AttributeError):
                        pass

            assigned_agent_id = None
            assignee_agent = None
            if assignee_name:
                stmt = select(Agent).where(
                    Agent.team_id == team_uuid,
                    Agent.name == assignee_name
                )
                result = await db.execute(stmt)
                assignee_agent = result.scalar_one_or_none()
                if assignee_agent:
                    assigned_agent_id = assignee_agent.id
                else:
                    return f"Error: No agent named '{assignee_name}' found in this team."

            task = Task(
                id=task_uuid,
                team_id=team_uuid,
                title=title,
                description=description,
                priority=priority,
                status=initial_status,
                assigned_agent_id=assigned_agent_id,
                blocked_by_task_id=primary_blocked_by,
                depends_on=clean_deps,
                created_by="agent",
                revision=1,
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)

            from core.tasks.board_service import notify_assignment, notify_unassigned_task, publish_task, record_task_activity
            agent_actor_name = creator_agent_name or "Agent"
            await record_task_activity(
                db, task, actor_id="agent", actor_name=agent_actor_name,
                activity_type="created", details=f"Task '{task.title}' created ({task.status}, {task.priority})",
                new_value={"title": task.title, "priority": task.priority, "status": task.status}
            )
            if assignee_agent:
                await record_task_activity(
                    db, task, actor_id="agent", actor_name=agent_actor_name,
                    activity_type="assigned", details=f"Assigned to {assignee_agent.name}",
                    new_value={"assigned_agent_id": str(assignee_agent.id), "assignee_name": assignee_agent.name}
                )

            await publish_task(task, "created")

            # If assigned, wake the agent via chat @mention (suppress if assigned to oneself)
            is_self_assignment = (
                assignee_agent is not None
                and creator_agent_name is not None
                and assignee_agent.name.strip().lower() == creator_agent_name.strip().lower()
            )
            if assignee_agent and not is_self_assignment:
                await notify_assignment(
                    db, task, actor_id=None, actor_name=creator_agent_name or "Agent",
                )
            elif not assignee_agent:
                await notify_unassigned_task(db, task, creator_agent_name or "Agent")

            assigned_msg = f" (assigned to {assignee_name})" if assignee_name else ""
            blocked_msg = f" [BLOCKED by {len(clean_deps)} prerequisite(s)]" if initial_status == "blocked" else ""
            return f"✓ Task created: '{title}' (ID: {task.id}){assigned_msg} [priority: {priority}]{blocked_msg}"

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
                deps_count = len(t.depends_on or [])
                dep_info = f" [deps: {deps_count}]" if deps_count > 0 else ""
                lines.append(f"  {icon} [{t.priority}] {t.title}{assignee}{dep_info} (id: {str(t.id)[:8]})")

            return "\n".join(lines)

    async def update_task(
        self, task_id: str, status: str = None, notes: str = None,
        assignee_name: str = None, agent_name: str = None,
        blocked_by_task_id: str = None, team_id: str = None,
        depends_on: Optional[List[str]] = None,
        expected_revision: Optional[int] = None,
        db: Optional[AsyncSession] = None,
    ) -> str:
        """Updates a task's status, notes, dependencies, and/or assignee. Wakes the agent on assignment."""
        if db is not None:
            return await self._execute_update_task(db, task_id, status, notes, assignee_name, agent_name, blocked_by_task_id, team_id, depends_on, expected_revision)
        async with async_session() as session:
            return await self._execute_update_task(session, task_id, status, notes, assignee_name, agent_name, blocked_by_task_id, team_id, depends_on, expected_revision)

    async def _execute_update_task(
        self, db: AsyncSession, task_id: str, status: str = None, notes: str = None,
        assignee_name: str = None, agent_name: str = None,
        blocked_by_task_id: str = None, team_id: str = None,
        depends_on: Optional[List[str]] = None,
        expected_revision: Optional[int] = None,
    ) -> str:
        task = await _resolve_task(db, task_id, team_id)
        if not task:
            return f"Error: Task '{task_id}' not found."

        if expected_revision is not None and (task.revision or 1) != expected_revision:
            return f"Error: Conflict (409). Task '{task.id}' revision is {task.revision or 1}, but expected revision was {expected_revision}."

        old_status = task.status
        old_assignee_id = task.assigned_agent_id
        old_deps = list(task.depends_on or [])
        team_id_str = str(task.team_id)

        # Update and validate dependencies if requested
        deps_changed = False
        if depends_on is not None or blocked_by_task_id is not None:
            stmt_team_tasks = select(Task).where(Task.team_id == task.team_id)
            team_tasks = (await db.execute(stmt_team_tasks)).scalars().all()

            new_deps: List[str] = []
            if depends_on is not None:
                for d in depends_on:
                    resolved_d = await _resolve_task(db, str(d), team_id_str)
                    d_id = str(resolved_d.id) if resolved_d else str(d).strip().lower()
                    if d_id and d_id not in new_deps:
                        new_deps.append(d_id)
            else:
                new_deps = list(task.depends_on or [])

            if blocked_by_task_id is not None:
                if blocked_by_task_id:
                    resolved_b = await _resolve_task(db, str(blocked_by_task_id), team_id_str)
                    b_id = str(resolved_b.id) if resolved_b else str(blocked_by_task_id).strip().lower()
                    if b_id and b_id not in new_deps:
                        new_deps.append(b_id)
                else:
                    task.blocked_by_task_id = None

            # Validate DAG acyclicity
            try:
                workflow_dag.validate_acyclic(
                    tasks=team_tasks,
                    new_or_updated_task_id=str(task.id),
                    new_dependencies=new_deps,
                )
            except DAGCycleError as e:
                return f"Error: Cannot update task dependencies — {str(e)}"

            if new_deps != old_deps:
                deps_changed = True
                task.depends_on = new_deps
                if new_deps and not task.blocked_by_task_id:
                    try:
                        task.blocked_by_task_id = uuid.UUID(new_deps[0])
                    except (ValueError, AttributeError):
                        pass

        status_changed = False
        if status:
            valid_statuses = {"todo", "in_progress", "review", "done", "blocked"}
            if status not in valid_statuses:
                return f"Error: Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}"
            if status != old_status:
                status_changed = True
                task.status = status

        if notes:
            comment = TaskComment(
                task_id=task.id,
                author_id="system",
                author_name=agent_name or "System",
                text=notes
            )
            db.add(comment)

        # Handle assignee change
        new_assignee_agent = None
        assignee_changed = False
        if assignee_name:
            a_stmt = select(Agent).where(
                Agent.team_id == task.team_id,
                Agent.name == assignee_name
            )
            a_res = await db.execute(a_stmt)
            new_assignee_agent = a_res.scalar_one_or_none()
            if new_assignee_agent:
                if task.assigned_agent_id != new_assignee_agent.id:
                    assignee_changed = True
                    task.assigned_agent_id = new_assignee_agent.id
            else:
                return f"Error: No agent named '{assignee_name}' found in this team."

        task.revision = (task.revision or 1) + 1
        task.updated_at = datetime.now(timezone.utc)

        from core.tasks.board_service import notify_assignment, publish_task, wake_agents, record_task_activity
        updater_actor_name = agent_name or "Agent"
        if status_changed:
            await record_task_activity(
                db, task, actor_id="agent", actor_name=updater_actor_name,
                activity_type="status_changed", details=f"Status changed from {old_status} to {task.status}",
                old_value=old_status, new_value=task.status,
            )
        if assignee_changed:
            await record_task_activity(
                db, task, actor_id="agent", actor_name=updater_actor_name,
                activity_type="assigned", details=f"Assigned to {new_assignee_agent.name if new_assignee_agent else 'None'}",
                new_value={"assigned_agent_id": str(new_assignee_agent.id) if new_assignee_agent else None, "assignee_name": new_assignee_agent.name if new_assignee_agent else None},
            )
        if deps_changed:
            await record_task_activity(
                db, task, actor_id="agent", actor_name=updater_actor_name,
                activity_type="dependencies_changed", details=f"Dependencies updated to {task.depends_on}",
                old_value=old_deps, new_value=task.depends_on,
            )

        await db.commit()
        await publish_task(task)

        # If a new assignee was set, wake them via @mention (suppress if assigned to oneself)
        is_self_update = (
            new_assignee_agent is not None
            and agent_name is not None
            and new_assignee_agent.name.strip().lower() == agent_name.strip().lower()
        )
        if new_assignee_agent and not is_self_update and assignee_changed:
            await notify_assignment(
                db, task, actor_id=None, actor_name=agent_name or "Agent",
            )

        # ── MULTI-DEPENDENCY UNBLOCK & CASCADE ENGINE ───────────────────────────
        all_team_tasks_stmt = select(Task).where(Task.team_id == task.team_id)
        all_team_tasks = (await db.execute(all_team_tasks_stmt)).scalars().all()

        if task.status == "done":
            # 1. Identify all downstream tasks whose dependencies are now fully satisfied
            unblocked_tasks = workflow_dag.propagate_task_completion(all_team_tasks, str(task.id))
            unblock_notifications = []

            for b_task in unblocked_tasks:
                b_task.blocked_by_task_id = None
                b_task.status = "todo"
                b_task.revision = (b_task.revision or 1) + 1
                b_task.updated_at = datetime.now(timezone.utc)
                await record_task_activity(
                    db, b_task, actor_id="system", actor_name="System",
                    activity_type="unblocked", details=f"Prerequisites satisfied by task '{task.title}'",
                    old_value="blocked", new_value="todo",
                )
                await publish_task(b_task, "updated")

                if b_task.assigned_agent_id:
                    agent_res = await db.execute(select(Agent).where(Agent.id == b_task.assigned_agent_id))
                    b_agent = agent_res.scalar_one_or_none()
                    if b_agent:
                        unblock_text = f"[TASK_UNBLOCKED] @{b_agent.name} prerequisite task '{task.title}' is complete. All prerequisites for '{b_task.title}' are now satisfied. You are unblocked and can begin work now. Use update_task(task_id='{b_task.id}', status='in_progress') to start."
                        unblock_notifications.append((b_agent, b_task, unblock_text))

            orchestrator_notification = None
            if not unblocked_tasks:
                # Check if ANY non-done tasks remain in the team
                remaining = [t for t in all_team_tasks if t.status != "done" and t.id != task.id]
                if not remaining:
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
                            f"All tasks on the board are now complete! Please deliver the final synthesis to the user."
                        )
                        orchestrator_notification = (orchestrator, done_text)

            await db.commit()

            # Dispatch unblock notifications
            for b_agent, b_task, unblock_text in unblock_notifications:
                await wake_agents(
                    db, b_task, [b_agent], reason="unblocked", actor_id=None,
                    actor_name=agent_name or "Agent", event_id=str(task.id),
                    coordination_context=unblock_text,
                )

            if orchestrator_notification:
                orch, done_text = orchestrator_notification
                await wake_agents(
                    db, task, [orch], reason="board_complete", actor_id=None,
                    actor_name=agent_name or "Agent", event_id=str(task.updated_at),
                    coordination_context=done_text,
                )

        elif task.status == "blocked":
            # 2. Propagate cascade failure to downstream tasks
            cascade_impacted = workflow_dag.propagate_cascade_failure(
                tasks=all_team_tasks,
                failed_task_id=str(task.id),
                reason=notes or f"Upstream prerequisite '{task.title}' is blocked",
            )
            for c_task, cascade_msg in cascade_impacted:
                if c_task.status != "blocked":
                    c_task.status = "blocked"
                    c_task.revision = (c_task.revision or 1) + 1
                    c_task.updated_at = datetime.now(timezone.utc)
                    await record_task_activity(
                        db, c_task, actor_id="system", actor_name="System",
                        activity_type="status_changed", details=f"Cascade blocked: {cascade_msg}",
                        old_value="todo", new_value="blocked",
                    )
                    await publish_task(c_task, "updated")
            if cascade_impacted:
                await db.commit()

        summary = f"✓ Task '{task.title}' updated: {old_status} → {task.status}"
        if new_assignee_agent:
            summary += f" | assigned to {new_assignee_agent.name}"
        return summary

    async def delete_task(
        self, task_id: str, author_id: str = "agent", author_name: str = "Agent", team_id: str = None
    ) -> str:
        """Deletes a task and cleans up dependencies across downstream tasks."""
        from core.tasks.board_service import delete_task_with_dependencies
        async with async_session() as db:
            task = await _resolve_task(db, task_id, team_id)
            if not task:
                return f"Error: Task '{task_id}' not found."
            task_title = task.title
            task_id_str = str(task.id)
            deleted = await delete_task_with_dependencies(db, task, author_id=author_id, author_name=author_name)
            if not deleted:
                return f"Error: Could not delete task '{task_id}'."
            return f"✓ Task '{task_title}' (ID: {task_id_str}) deleted."

    async def comment_on_task(
        self, task_id: str, text: str, author_id: str, author_name: str, team_id: str = None,
        db: Optional[AsyncSession] = None,
    ) -> str:
        """Adds a comment to a task and broadcasts a chat notification."""
        if db is not None:
            return await self._execute_comment_on_task(db, task_id, text, author_id, author_name, team_id)
        async with async_session() as session:
            return await self._execute_comment_on_task(session, task_id, text, author_id, author_name, team_id)

    async def _execute_comment_on_task(
        self, db: AsyncSession, task_id: str, text: str, author_id: str, author_name: str, team_id: str = None
    ) -> str:
        from core.tasks.board_service import add_comment
        task = await _resolve_task(db, task_id, team_id)
        if not task:
            return f"Error: Task '{task_id}' not found."
        try:
            _, woken = await add_comment(
                db, task, author_id=author_id, author_name=author_name, text=text,
            )
        except ValueError as exc:
            return f"Error: {exc}"
        return f"✓ Comment added to task '{task.title}' ({len(woken)} agent(s) notified)"

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
