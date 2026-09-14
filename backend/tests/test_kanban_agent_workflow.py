# -*- coding: utf-8 -*-
"""
Comprehensive test suite for the Kanban Agent Workflow:
- Wake policy acceptance scenarios 1-8
- Production follow-up items 1-7:
  1. Transactional Outbox, Idempotency & Stale Lease Reclamation
  2. Per-user Read Cursors & Task Watchers
  3. Task Activity Records (Audit Log, Zero Model Token Overhead)
  4. Notification Preferences & Muted Tasks
  5. Optimistic Concurrency with Revision (409 Conflict Rejection)
  6. Ephemeral WebSocket Events
  7. Operational Metrics & Summary
"""

import uuid
import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from unittest.mock import patch, AsyncMock

from core.memory.database import async_session
from core.memory.models import (
    User, Project, Team, Agent, Task, TaskComment,
    TaskOutboxEvent, TaskWatcher, TaskReadCursor,
    TaskActivity, AgentNotificationPreference, TaskMetric
)
from core.tasks.board_service import (
    notify_assignment, notify_unassigned_task, add_comment,
    delete_task_with_dependencies, dispatch_pending_outbox,
    mark_task_read, get_task_unread_counts, record_task_metric,
    task_payload
)
from core.tools.task_tools import task_tools
from core.chat.message_router import message_router


@pytest.fixture(autouse=True)
async def mock_agent_worker_and_cleanup():
    """Mock agent worker loop so tests do not invoke LLMs or hang on worker loops."""
    worker_hold_event = asyncio.Event()

    async def _mock_worker(*args, **kwargs):
        try:
            await worker_hold_event.wait()
        except asyncio.CancelledError:
            pass

    with patch.object(message_router, "_agent_worker", side_effect=_mock_worker):
        yield

    worker_hold_event.set()
    await asyncio.sleep(0)
    for worker_task in list(message_router._workers.values()):
        if not worker_task.done():
            worker_task.cancel()
    await asyncio.sleep(0)
    message_router._workers.clear()
    message_router._queues.clear()
    message_router._pending.clear()
    message_router._pending_keys.clear()


async def _create_test_fixture(client):
    """Creates a user, project, team, and two agents for testing."""
    uid = uuid.uuid4()
    signup = await client.post(
        "/api/auth/signup",
        json={"email": f"user-{uid}@example.com", "password": "Password123!"}
    )
    assert signup.status_code == 200
    account = signup.json()
    headers = {"Authorization": f"Bearer {account['token']}"}
    user_id = account["user"]["id"]

    project = (await client.post("/api/projects", json={"name": f"Project-{uid}"}, headers=headers)).json()
    team = (await client.post("/api/teams", json={"name": f"Team-{uid}", "project_id": project["id"]}, headers=headers)).json()
    team_id = team["id"]

    agent_a = (await client.post(
        "/api/agents",
        json={"name": "Agent A", "role": "developer", "team_id": team_id, "model": "openrouter/free"},
        headers=headers
    )).json()

    agent_b = (await client.post(
        "/api/agents",
        json={"name": "Agent B", "role": "tester", "team_id": team_id, "model": "openrouter/free"},
        headers=headers
    )).json()

    return {
        "headers": headers,
        "user_id": user_id,
        "team_id": team_id,
        "agent_a": agent_a,
        "agent_b": agent_b,
    }


@pytest.mark.asyncio
async def test_scenario_1_assign_unblocked_task(client):
    """Scenario 1: Assign an unblocked task -> exactly 1 wake, outbox event recorded."""
    fx = await _create_test_fixture(client)
    res = await client.post(
        "/api/tasks",
        json={
            "team_id": fx["team_id"],
            "title": "Build Auth Module",
            "description": "Create JWT auth.",
            "priority": "high",
            "assigned_agent_id": fx["agent_a"]["id"],
        },
        headers=fx["headers"]
    )
    assert res.status_code == 200, res.text
    task_data = res.json()
    assert task_data["status"] == "todo"
    assert task_data["revision"] == 1

    # Check outbox event was created and dispatched
    async with async_session() as db:
        events = (await db.execute(
            select(TaskOutboxEvent).where(
                TaskOutboxEvent.task_id == uuid.UUID(task_data["id"]),
                TaskOutboxEvent.agent_id == uuid.UUID(fx["agent_a"]["id"]),
            )
        )).scalars().all()
        assert len(events) == 1
        ev = events[0]
        assert ev.status in ("completed", "sent")
        assert "Build Auth Module" in ev.prompt


@pytest.mark.asyncio
async def test_scenario_2_resave_same_assignment(client):
    """Scenario 2: Re-saving same assignment results in 0 new wakeups."""
    fx = await _create_test_fixture(client)
    created = (await client.post(
        "/api/tasks",
        json={
            "team_id": fx["team_id"],
            "title": "Static Config Setup",
            "priority": "medium",
            "assigned_agent_id": fx["agent_a"]["id"],
        },
        headers=fx["headers"]
    )).json()

    # Clear or count outbox events
    async with async_session() as db:
        initial_events = (await db.execute(
            select(TaskOutboxEvent).where(TaskOutboxEvent.task_id == uuid.UUID(created["id"]))
        )).scalars().all()
        assert len(initial_events) == 1

    # Update task with same assignee and same status
    res = await client.put(
        f"/api/tasks/{created['id']}",
        json={
            "description": "Updated notes only",
            "assigned_agent_id": fx["agent_a"]["id"],
            "status": "todo",
            "expected_revision": created["revision"],
        },
        headers=fx["headers"]
    )
    assert res.status_code == 200, res.text
    assert res.json()["revision"] == 2

    # Verify no new assignment outbox events
    async with async_session() as db:
        events_after = (await db.execute(
            select(TaskOutboxEvent).where(
                TaskOutboxEvent.task_id == uuid.UUID(created["id"]),
                TaskOutboxEvent.dedupe_key.like("board:assigned:%"),
            )
        )).scalars().all()
        assert len(events_after) == 1


@pytest.mark.asyncio
async def test_scenario_3_assign_blocked_task_and_unblock(client):
    """Scenario 3: Assign a blocked task -> 0 wakeups while blocked; unblock -> 1 wakeup."""
    fx = await _create_test_fixture(client)

    # Task A (Prerequisite)
    task_a = (await client.post(
        "/api/tasks",
        json={"team_id": fx["team_id"], "title": "Prerequisite Task A", "priority": "high"},
        headers=fx["headers"]
    )).json()

    # Task B depends on Task A
    task_b = (await client.post(
        "/api/tasks",
        json={
            "team_id": fx["team_id"],
            "title": "Dependent Task B",
            "assigned_agent_id": fx["agent_b"]["id"],
            "depends_on": [task_a["id"]],
        },
        headers=fx["headers"]
    )).json()

    assert task_b["status"] == "blocked"

    # Agent B should NOT be woken while task is blocked
    async with async_session() as db:
        events = (await db.execute(
            select(TaskOutboxEvent).where(
                TaskOutboxEvent.task_id == uuid.UUID(task_b["id"]),
                TaskOutboxEvent.agent_id == uuid.UUID(fx["agent_b"]["id"]),
            )
        )).scalars().all()
        assert len(events) == 0

    # Mark Task A as done
    res = await client.put(
        f"/api/tasks/{task_a['id']}",
        json={"status": "done", "expected_revision": task_a["revision"]},
        headers=fx["headers"]
    )
    assert res.status_code == 200

    # Task B should now be unblocked ('todo') and Agent B woken once
    async with async_session() as db:
        tb_refreshed = await db.get(Task, uuid.UUID(task_b["id"]))
        assert tb_refreshed.status == "todo"

        b_events = (await db.execute(
            select(TaskOutboxEvent).where(
                TaskOutboxEvent.task_id == uuid.UUID(task_b["id"]),
                TaskOutboxEvent.agent_id == uuid.UUID(fx["agent_b"]["id"]),
            )
        )).scalars().all()
        assert len(b_events) == 1
        assert "[TASK_UNBLOCKED]" in b_events[0].prompt


@pytest.mark.asyncio
async def test_scenario_4_human_comment_wakes_assignee(client):
    """Scenario 4: Human comment wakes assignee once without duplicate prompts."""
    fx = await _create_test_fixture(client)
    task = (await client.post(
        "/api/tasks",
        json={
            "team_id": fx["team_id"],
            "title": "Review PR",
            "assigned_agent_id": fx["agent_a"]["id"],
        },
        headers=fx["headers"]
    )).json()

    # Post a human comment
    c_res = await client.post(
        f"/api/tasks/{task['id']}/comments",
        json={"text": "Please check line 42."},
        headers=fx["headers"]
    )
    assert c_res.status_code == 200

    async with async_session() as db:
        events = (await db.execute(
            select(TaskOutboxEvent).where(
                TaskOutboxEvent.task_id == uuid.UUID(task["id"]),
                TaskOutboxEvent.agent_id == uuid.UUID(fx["agent_a"]["id"]),
                TaskOutboxEvent.dedupe_key.like("board:comment:%"),
            )
        )).scalars().all()
        assert len(events) == 1
        assert "Please check line 42." in events[0].prompt


@pytest.mark.asyncio
async def test_scenario_5_comment_mentions_multiple_agents(client):
    """Scenario 5: Comment mentions multiple agents -> assignee and tagged agents each wake once."""
    fx = await _create_test_fixture(client)
    task = (await client.post(
        "/api/tasks",
        json={
            "team_id": fx["team_id"],
            "title": "Cross-Team Feature",
            "assigned_agent_id": fx["agent_a"]["id"],
        },
        headers=fx["headers"]
    )).json()

    # Comment tags @Agent A and @Agent B
    c_res = await client.post(
        f"/api/tasks/{task['id']}/comments",
        json={"text": "@Agent A and @Agent B please align on this schema."},
        headers=fx["headers"]
    )
    assert c_res.status_code == 200

    async with async_session() as db:
        # Agent A: exactly 1 comment wakeup (no duplicates despite being assignee AND mentioned)
        a_events = (await db.execute(
            select(TaskOutboxEvent).where(
                TaskOutboxEvent.task_id == uuid.UUID(task["id"]),
                TaskOutboxEvent.agent_id == uuid.UUID(fx["agent_a"]["id"]),
                TaskOutboxEvent.dedupe_key.like("board:comment:%"),
            )
        )).scalars().all()
        assert len(a_events) == 1

        # Agent B: exactly 1 comment wakeup
        b_events = (await db.execute(
            select(TaskOutboxEvent).where(
                TaskOutboxEvent.task_id == uuid.UUID(task["id"]),
                TaskOutboxEvent.agent_id == uuid.UUID(fx["agent_b"]["id"]),
                TaskOutboxEvent.dedupe_key.like("board:comment:%"),
            )
        )).scalars().all()
        assert len(b_events) == 1


@pytest.mark.asyncio
async def test_scenario_6_agent_comment_author_suppression(client):
    """Scenario 6: Agent B comments and tags Agent A -> Agent A wakes, Agent B does not self-trigger."""
    fx = await _create_test_fixture(client)
    task = (await client.post(
        "/api/tasks",
        json={"team_id": fx["team_id"], "title": "Self-trigger Check"},
        headers=fx["headers"]
    )).json()

    # Agent B comments directly via task_tools
    async with async_session() as db:
        t_obj = await db.get(Task, uuid.UUID(task["id"]))
        comment_res, woken = await add_comment(
            db, t_obj,
            author_id=fx["agent_b"]["id"],
            author_name="Agent B",
            text="Hey @Agent A take a look.",
        )
        await db.commit()

    # Woken agents should be Agent A only; Agent B must NOT be woken
    woken_ids = [str(a) for a in woken]
    assert fx["agent_a"]["id"] in woken_ids
    assert fx["agent_b"]["id"] not in woken_ids


@pytest.mark.asyncio
async def test_scenario_7_delete_prerequisite_unblocks(client):
    """Scenario 7: Deleting prerequisite task unblocks downstream task and wakes assignee."""
    fx = await _create_test_fixture(client)

    task_a = (await client.post(
        "/api/tasks",
        json={"team_id": fx["team_id"], "title": "Prereq To Delete"},
        headers=fx["headers"]
    )).json()

    task_b = (await client.post(
        "/api/tasks",
        json={
            "team_id": fx["team_id"],
            "title": "Blocked on Deleted",
            "assigned_agent_id": fx["agent_b"]["id"],
            "depends_on": [task_a["id"]],
        },
        headers=fx["headers"]
    )).json()
    assert task_b["status"] == "blocked"

    # Delete Task A
    del_res = await client.delete(f"/api/tasks/{task_a['id']}", headers=fx["headers"])
    assert del_res.status_code == 200

    # Task B should be unblocked to 'todo' and Agent B woken
    async with async_session() as db:
        tb = await db.get(Task, uuid.UUID(task_b["id"]))
        assert tb.status == "todo"
        assert task_a["id"] not in (tb.depends_on or [])

        unblock_events = (await db.execute(
            select(TaskOutboxEvent).where(
                TaskOutboxEvent.task_id == uuid.UUID(task_b["id"]),
                TaskOutboxEvent.agent_id == uuid.UUID(fx["agent_b"]["id"]),
                TaskOutboxEvent.dedupe_key.like("board:unblocked:%"),
            )
        )).scalars().all()
        assert len(unblock_events) == 1


@pytest.mark.asyncio
async def test_scenario_8_rest_state_consistency(client):
    """Scenario 8: GET /tasks/{team_id} matches canonical payload including revision."""
    fx = await _create_test_fixture(client)
    created = (await client.post(
        "/api/tasks",
        json={"team_id": fx["team_id"], "title": "Consistency Task", "priority": "low"},
        headers=fx["headers"]
    )).json()

    list_res = await client.get(f"/api/tasks/{fx['team_id']}", headers=fx["headers"])
    assert list_res.status_code == 200
    all_tasks = list_res.json()
    matched = next((t for t in all_tasks if t["id"] == created["id"]), None)
    assert matched is not None
    assert matched["revision"] == 1
    assert "depends_on" in matched
    assert "status" in matched


@pytest.mark.asyncio
async def test_production_item_1_outbox_stale_lease(client):
    """Production Item 1: Outbox persistence, dispatch, and stale lease reclamation."""
    fx = await _create_test_fixture(client)
    task = (await client.post(
        "/api/tasks",
        json={"team_id": fx["team_id"], "title": "Stale Outbox Task"},
        headers=fx["headers"]
    )).json()

    # Insert a simulated stale leased event in outbox
    stale_event_id = f"board:test:stale:{uuid.uuid4()}"
    async with async_session() as db:
        stale_ev = TaskOutboxEvent(
            event_id=stale_event_id,
            team_id=uuid.UUID(fx["team_id"]),
            task_id=uuid.UUID(task["id"]),
            agent_id=uuid.UUID(fx["agent_a"]["id"]),
            dedupe_key="test:dedupe:stale",
            prompt="[TASK_TEST] Stale prompt test",
            reason="assigned",
            status="processing",
            lease_timeout=datetime.now(timezone.utc) - timedelta(minutes=5),  # expired
            retry_count=0,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=6),
        )
        db.add(stale_ev)
        await db.commit()

    # Run outbox dispatcher
    dispatched = await dispatch_pending_outbox()
    assert dispatched >= 1

    # Stale event should have been reclaimed and set to 'completed'
    async with async_session() as db:
        ev = (await db.execute(
            select(TaskOutboxEvent).where(TaskOutboxEvent.event_id == stale_event_id)
        )).scalar_one_or_none()
        assert ev is not None
        assert ev.status in ("completed", "sent")


@pytest.mark.asyncio
async def test_production_item_2_read_cursors_and_watchers(client):
    """Production Item 2: Watchers and read cursors with unread counts."""
    fx = await _create_test_fixture(client)
    task = (await client.post(
        "/api/tasks",
        json={"team_id": fx["team_id"], "title": "Watchable Task"},
        headers=fx["headers"]
    )).json()

    # 1. Watch task
    w_res = await client.post(f"/api/tasks/{task['id']}/watch", headers=fx["headers"])
    assert w_res.status_code == 200
    assert w_res.json()["watching"] is True

    # 2. Get watchers
    watchers_res = await client.get(f"/api/tasks/{task['id']}/watchers", headers=fx["headers"])
    assert watchers_res.status_code == 200
    assert fx["user_id"] in watchers_res.json()["watchers"]
    assert watchers_res.json()["is_watching"] is True

    # 3. Add comment
    await client.post(
        f"/api/tasks/{task['id']}/comments",
        json={"text": "Unread comment 1"},
        headers=fx["headers"]
    )

    # 4. Unread counts before marking read
    counts_res = await client.get(f"/api/teams/{fx['team_id']}/tasks/unread-counts", headers=fx["headers"])
    assert counts_res.status_code == 200
    assert counts_res.json().get(task["id"], 0) >= 1

    # 5. Mark read
    read_res = await client.post(f"/api/tasks/{task['id']}/read", headers=fx["headers"])
    assert read_res.status_code == 200

    # 6. Unread counts after marking read should be 0
    counts_after = (await client.get(f"/api/teams/{fx['team_id']}/tasks/unread-counts", headers=fx["headers"])).json()
    assert counts_after.get(task["id"], 0) == 0

    # 7. Unwatch task
    unw_res = await client.delete(f"/api/tasks/{task['id']}/watch", headers=fx["headers"])
    assert unw_res.status_code == 200
    assert unw_res.json()["watching"] is False


@pytest.mark.asyncio
async def test_production_item_3_task_activities_audit_trail(client):
    """Production Item 3: Task Activity audit logs created without model prompt pollution."""
    fx = await _create_test_fixture(client)
    task = (await client.post(
        "/api/tasks",
        json={
            "team_id": fx["team_id"],
            "title": "Audited Task",
            "priority": "low",
            "assigned_agent_id": fx["agent_a"]["id"],
        },
        headers=fx["headers"]
    )).json()

    # Update status to in_progress
    await client.put(
        f"/api/tasks/{task['id']}",
        json={"status": "in_progress", "expected_revision": 1},
        headers=fx["headers"]
    )

    # Add comment
    await client.post(
        f"/api/tasks/{task['id']}/comments",
        json={"text": "Audit test comment"},
        headers=fx["headers"]
    )

    # Retrieve activities
    act_res = await client.get(f"/api/tasks/{task['id']}/activities", headers=fx["headers"])
    assert act_res.status_code == 200
    activities = act_res.json()
    types = [a["activity_type"] for a in activities]
    assert "created" in types
    assert "status_changed" in types
    assert "comment_added" in types


@pytest.mark.asyncio
async def test_production_item_4_notification_preferences_and_mute(client):
    """Production Item 4: Agent notification preferences and task mute suppression."""
    fx = await _create_test_fixture(client)
    task = (await client.post(
        "/api/tasks",
        json={
            "team_id": fx["team_id"],
            "title": "Muted Task",
            "assigned_agent_id": fx["agent_a"]["id"],
        },
        headers=fx["headers"]
    )).json()

    # Mute task for Agent A
    mute_res = await client.post(
        f"/api/tasks/{task['id']}/mute?agent_id={fx['agent_a']['id']}",
        headers=fx["headers"]
    )
    assert mute_res.status_code == 200
    assert mute_res.json()["muted"] is True

    # Post comment
    await client.post(
        f"/api/tasks/{task['id']}/comments",
        json={"text": "Message that should not wake muted agent"},
        headers=fx["headers"]
    )

    # Agent A must NOT have a comment wakeup event for this task
    async with async_session() as db:
        evs = (await db.execute(
            select(TaskOutboxEvent).where(
                TaskOutboxEvent.task_id == uuid.UUID(task["id"]),
                TaskOutboxEvent.agent_id == uuid.UUID(fx["agent_a"]["id"]),
                TaskOutboxEvent.dedupe_key.like("board:comment:%"),
            )
        )).scalars().all()
        assert len(evs) == 0


@pytest.mark.asyncio
async def test_production_item_5_optimistic_concurrency_409(client):
    """Production Item 5: Optimistic concurrency rejects stale revision with 409 Conflict."""
    fx = await _create_test_fixture(client)
    task = (await client.post(
        "/api/tasks",
        json={"team_id": fx["team_id"], "title": "Revision Guard Task"},
        headers=fx["headers"]
    )).json()
    assert task["revision"] == 1

    # Stale revision update attempt -> 409 Conflict
    conflict_res = await client.put(
        f"/api/tasks/{task['id']}",
        json={"title": "Stale update", "expected_revision": 999},
        headers=fx["headers"]
    )
    assert conflict_res.status_code == 409

    # Valid revision update -> 200 OK, bumps revision to 2
    ok_res = await client.put(
        f"/api/tasks/{task['id']}",
        json={"title": "Valid update", "expected_revision": 1},
        headers=fx["headers"]
    )
    assert ok_res.status_code == 200
    assert ok_res.json()["revision"] == 2


@pytest.mark.asyncio
async def test_production_item_6_operational_metrics(client):
    """Production Item 7: Operational metrics recording and summary endpoint."""
    fx = await _create_test_fixture(client)
    t_id = uuid.UUID(fx["team_id"])

    async with async_session() as db:
        await record_task_metric(db, team_id=t_id, metric_name="queue_delay", metric_value=0.25)
        await record_task_metric(db, team_id=t_id, metric_name="duplicate_suppression", metric_value=1.0)
        await record_task_metric(db, team_id=t_id, metric_name="task_completion", metric_value=1.0)
        await record_task_metric(db, team_id=t_id, metric_name="wake_reason", metric_value=1.0, tags={"reason": "assigned"})
        await db.commit()

    summary_res = await client.get(f"/api/teams/{fx['team_id']}/task-metrics/summary", headers=fx["headers"])
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["task_completions"] >= 1
    assert summary["duplicate_suppressions"] >= 1
    assert summary["wake_reason_distribution"].get("assigned", 0) >= 1
