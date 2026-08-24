"""
# backend/tests/test_cost_cron_notifs.py

Comprehensive test suite covering:
1. Cost Management & Token Usage aggregation (/api/cost)
2. Notification Center (/api/notifications)
3. Cron Scheduled Tasks (/api/cron)
"""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch
from tests.conftest import TestSession
from core.memory.models import TokenUsage, Notification, ScheduledTask


async def create_authenticated_user(client: AsyncClient, email: str = "cost_tester@carole.ai"):
    signup_payload = {
        "email": email,
        "password": "StrongPassword123!",
        "first_name": "Cost",
        "last_name": "Admin",
    }
    res = await client.post("/api/auth/signup", json=signup_payload)
    data = res.json()
    token = data["token"]
    user_id = data["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers, user_id, email


# ============================================================
# 1. Cost Management & Token Usage Tests
# ============================================================

@pytest.mark.asyncio
async def test_cost_management_and_token_stats(client: AsyncClient, db_session: AsyncSession):
    headers, user_id, email = await create_authenticated_user(client, "cost_user@carole.ai")

    # Create Project
    p_res = await client.post("/api/projects", json={"name": "Cost Proj", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]

    # 1. Update Project Budget Limit
    budget_res = await client.post(
        "/api/cost/budget",
        json={"project_id": project_id, "budget_limit_usd": 25.50},
        headers=headers
    )
    assert budget_res.status_code == 200
    assert budget_res.json()["status"] == "success"

    # 2. Insert Token Usage Records using db_session fixture
    usage1 = TokenUsage(
        project_id=uuid.UUID(project_id),
        model="claude-3.5-sonnet",
        provider="anthropic",
        prompt_tokens=1500,
        completion_tokens=500,
        total_tokens=2000,
        estimated_cost_usd=0.015
    )
    usage2 = TokenUsage(
        project_id=uuid.UUID(project_id),
        model="gpt-4o-mini",
        provider="openai",
        prompt_tokens=800,
        completion_tokens=200,
        total_tokens=1000,
        estimated_cost_usd=0.002
    )
    db_session.add_all([usage1, usage2])
    await db_session.commit()

    # 3. Retrieve Aggregated Cost Stats
    stats_res = await client.get(f"/api/cost/stats?project_id={project_id}", headers=headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["budget_limit_usd"] == 25.50
    assert stats["total_prompt_tokens"] == 2300
    assert stats["total_completion_tokens"] == 700
    assert stats["total_tokens"] == 3000


# ============================================================
# 2. Notification Center Tests
# ============================================================

@pytest.mark.asyncio
async def test_notifications_lifecycle(client: AsyncClient, db_session: AsyncSession):
    headers, user_id, email = await create_authenticated_user(client, "notif_user@carole.ai")

    # 1. Insert Sample Notifications for this user using db_session
    n1 = Notification(
        user_id=user_id,
        title="Agent Finished Task",
        message="Coder completed database migration.",
        type="success",
        is_read=False
    )
    n2 = Notification(
        user_id=user_id,
        title="Approval Required",
        message="Reviewer requests bash execution.",
        type="warning",
        is_read=False
    )
    db_session.add_all([n1, n2])
    await db_session.commit()
    await db_session.refresh(n1)
    await db_session.refresh(n2)
    n1_id = str(n1.id)
    n2_id = str(n2.id)

    # 2. List Notifications -> 2 unread
    list_res = await client.get("/api/notifications", headers=headers)
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["unread_count"] == 2
    assert len(data["notifications"]) == 2

    # 3. Mark single notification as read
    mark_res = await client.post("/api/notifications/read", json={"notification_id": n1_id}, headers=headers)
    assert mark_res.status_code == 200

    # Verify unread count is now 1
    list_res2 = await client.get("/api/notifications", headers=headers)
    assert list_res2.json()["unread_count"] == 1

    # 4. Mark all as read
    mark_all_res = await client.post("/api/notifications/read", json={}, headers=headers)
    assert mark_all_res.status_code == 200

    list_res3 = await client.get("/api/notifications", headers=headers)
    assert list_res3.json()["unread_count"] == 0

    # 5. Delete single notification
    del_res = await client.delete(f"/api/notifications/{n1_id}", headers=headers)
    assert del_res.status_code == 200

    # 6. Clear all notifications
    clear_res = await client.delete("/api/notifications", headers=headers)
    assert clear_res.status_code == 200

    list_res4 = await client.get("/api/notifications", headers=headers)
    assert len(list_res4.json()["notifications"]) == 0


# ============================================================
# 3. Cron Scheduled Tasks Tests
# ============================================================

@pytest.mark.asyncio
async def test_cron_scheduled_tasks_lifecycle(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "cron_user@carole.ai")

    # Setup Project, Team, Agent
    p_res = await client.post("/api/projects", json={"name": "Cron Proj", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]
    t_res = await client.post("/api/teams", json={"name": "Cron Team", "project_id": project_id}, headers=headers)
    team_id = t_res.json()["id"]
    with patch("core.chat.message_router.async_session", TestSession):
        a_res = await client.post("/api/agents", json={
            "team_id": team_id, "name": "Cron Bot", "role": "Coder", "model": "openrouter/free"
        }, headers=headers)
    agent_id = a_res.json()["id"]

    # 1. Create Scheduled Task
    create_payload = {
        "name": "Hourly Health Check",
        "agent_id": agent_id,
        "cron_expression": "0 * * * *",
        "prompt": "Check repo health and log summary."
    }
    cron_create_res = await client.post(f"/api/cron/{team_id}", json=create_payload, headers=headers)
    assert cron_create_res.status_code == 200
    cron_task = cron_create_res.json()
    assert cron_task["name"] == "Hourly Health Check"
    assert cron_task["cron_expression"] == "0 * * * *"
    assert cron_task["is_active"] is True
    cron_id = cron_task["id"]

    # 2. List Scheduled Tasks
    cron_list = await client.get(f"/api/cron/{team_id}", headers=headers)
    assert cron_list.status_code == 200
    assert len(cron_list.json()) == 1
    assert cron_list.json()[0]["id"] == cron_id

    # 3. Update Scheduled Task
    update_res = await client.put(
        f"/api/cron/{cron_id}",
        json={"is_active": False, "name": "Disabled Health Check"},
        headers=headers
    )
    assert update_res.status_code == 200
    assert update_res.json()["is_active"] is False
    assert update_res.json()["name"] == "Disabled Health Check"

    # 4. Delete Scheduled Task
    del_cron = await client.delete(f"/api/cron/{cron_id}", headers=headers)
    assert del_cron.status_code == 200

    # Verify deleted
    cron_list2 = await client.get(f"/api/cron/{team_id}", headers=headers)
    assert len(cron_list2.json()) == 0
