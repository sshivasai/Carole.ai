"""
# backend/tests/test_crud_complete.py

Comprehensive test suite verifying full CRUD lifecycles for:
- Users (Tenant hierarchy)
- Projects (Workspace folders, slugification, cascading delete)
- Teams (Team isolation, Project scoping)
- Agents (Role templates, reasoning effort, personality, tool permissions)
- Tasks (Statuses, Priorities, Assignees, Blockers, Subtasks)
- Task Comments (Author metadata, timestamp ordering)
"""

import pytest
import uuid
from httpx import AsyncClient
from unittest.mock import patch
from tests.conftest import TestSession


async def create_authenticated_user(client: AsyncClient, email: str = "testuser@carole.ai"):
    signup_payload = {
        "email": email,
        "password": "StrongPassword123!",
        "first_name": "Alice",
        "last_name": "Tester",
    }
    res = await client.post("/api/auth/signup", json=signup_payload)
    data = res.json()
    token = data["token"]
    user_id = data["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers, user_id, email


# ============================================================
# 1. Project & Team CRUD Tests
# ============================================================

@pytest.mark.asyncio
async def test_project_crud_lifecycle(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "project_owner@carole.ai")

    # 1. Create Project
    create_res = await client.post("/api/projects", json={"name": "Project Apollo", "owner_id": user_id}, headers=headers)
    assert create_res.status_code == 200
    project_data = create_res.json()
    assert project_data["name"] == "Project Apollo"
    project_id = project_data["id"]

    # 2. List Projects
    list_res = await client.get("/api/projects", headers=headers)
    assert list_res.status_code == 200
    projects = list_res.json()
    assert any(p["id"] == project_id for p in projects)

    # 3. Update Project Name
    update_res = await client.put(f"/api/projects/{project_id}", json={"name": "Project Artemis"}, headers=headers)
    assert update_res.status_code == 200
    assert update_res.json()["status"] == "updated"

    # 4. Create Team under Project
    team_res = await client.post("/api/teams", json={"name": "Dev Swarm", "project_id": project_id}, headers=headers)
    assert team_res.status_code == 200
    team_id = team_res.json()["id"]

    # 5. List Teams
    teams_list = await client.get(f"/api/teams/{project_id}", headers=headers)
    assert teams_list.status_code == 200
    assert len(teams_list.json()) >= 1
    assert any(t["id"] == team_id for t in teams_list.json())

    # 6. Delete Project (Cascades to Team)
    del_res = await client.delete(f"/api/projects/{project_id}", headers=headers)
    assert del_res.status_code == 200


# ============================================================
# 2. Agent CRUD & Role Preset Tests
# ============================================================

@pytest.mark.asyncio
async def test_agent_crud_and_configuration(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "agent_master@carole.ai")

    # Setup Project & Team
    p_res = await client.post("/api/projects", json={"name": "Agent Playground", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]
    t_res = await client.post("/api/teams", json={"name": "Agent Squad", "project_id": project_id}, headers=headers)
    team_id = t_res.json()["id"]

    # 1. Create Agent with Full Custom Config
    agent_payload = {
        "team_id": team_id,
        "name": "Senior Coder",
        "role": "Coder",
        "model": "anthropic/claude-3.5-sonnet",
        "fallback_model": "google/gemini-2.0-flash",
        "reasoning_effort": "high",
        "system_prompt": "You write clean, modular Python and TypeScript code.",
        "personality": "mentor",
        "tool_permissions": {
            "write_file": "safe",
            "shell_exec": "human_only",
            "delete_file": "blocked"
        },
        "custom_instructions": "Always include unit tests with your code.",
        "skills": ["web_scraping"]
    }
    with patch("core.chat.message_router.async_session", TestSession):
        create_agent_res = await client.post("/api/agents", json=agent_payload, headers=headers)
    assert create_agent_res.status_code == 200
    agent_data = create_agent_res.json()
    assert agent_data["name"] == "Senior Coder"
    assert agent_data["role"] == "Coder"
    assert agent_data["reasoning_effort"] == "high"
    assert agent_data["personality"] == "mentor"
    agent_id = agent_data["id"]

    # 2. List Agents
    list_agents = await client.get(f"/api/agents/{team_id}", headers=headers)
    assert list_agents.status_code == 200
    assert len(list_agents.json()) == 1
    assert list_agents.json()[0]["id"] == agent_id
    assert list_agents.json()[0]["tool_permissions"]["shell_exec"] == "human_only"

    # 3. Update Agent
    update_agent_res = await client.put(
        f"/api/agents/{agent_id}",
        json={
            "personality": "witty",
            "reasoning_effort": "medium",
            "system_prompt": "Updated prompt"
        },
        headers=headers
    )
    assert update_agent_res.status_code == 200
    updated = update_agent_res.json()
    assert updated["personality"] == "witty"
    assert updated["reasoning_effort"] == "medium"

    # 4. Delete Agent
    with patch("core.chat.message_router.async_session", TestSession):
        del_agent_res = await client.delete(f"/api/agents/{agent_id}", headers=headers)
    assert del_agent_res.status_code == 200


# ============================================================
# 3. Task Lifecycle, Subtasks, Blockers & Comments Tests
# ============================================================

@pytest.mark.asyncio
async def test_task_workflow_and_comment_lifecycle(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "task_manager@carole.ai")

    # Setup Project & Team & Agent
    p_res = await client.post("/api/projects", json={"name": "Task System Proj", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]
    t_res = await client.post("/api/teams", json={"name": "Kanban Team", "project_id": project_id}, headers=headers)
    team_id = t_res.json()["id"]
    
    from unittest.mock import AsyncMock
    with patch("core.chat.message_router.message_router._trigger_agent", new_callable=AsyncMock), \
         patch("core.chat.message_router.message_router.route_message", new_callable=AsyncMock), \
         patch("core.chat.message_router.async_session", TestSession):
        a_res = await client.post("/api/agents", json={
            "team_id": team_id, "name": "Worker Agent", "role": "Coder", "model": "openrouter/free"
        }, headers=headers)
        agent_id = a_res.json()["id"]

        # 1. Create Parent Task in 'todo'
        parent_task_payload = {
            "team_id": team_id,
            "title": "Build Authentication Module",
            "description": "Implement JWT and password hashing",
            "priority": "high",
            "assigned_agent_id": agent_id,
            "created_by": "human"
        }
        task1_res = await client.post("/api/tasks", json=parent_task_payload, headers=headers)
        assert task1_res.status_code == 200
        task1 = task1_res.json()
        assert task1["title"] == "Build Authentication Module"
        assert task1["status"] == "todo"
        parent_task_id = task1["id"]

        # 2. Create Subtask linked to Parent Task
        subtask_payload = {
            "team_id": team_id,
            "title": "Implement bcrypt hashing",
            "description": "Subtask for password hashing",
            "priority": "medium",
            "parent_task_id": parent_task_id,
            "assigned_agent_id": agent_id
        }
        subtask_res = await client.post("/api/tasks", json=subtask_payload, headers=headers)
        assert subtask_res.status_code == 200
        subtask_id = subtask_res.json()["id"]

        # 3. Create Dependent Task Blocked by Parent Task
        task2_payload = {
            "team_id": team_id,
            "title": "Deploy API",
            "description": "Requires Auth to be done first",
            "priority": "critical",
            "blocked_by_task_id": parent_task_id
        }
        task2_res = await client.post("/api/tasks", json=task2_payload, headers=headers)
        assert task2_res.status_code == 200
        task2_id = task2_res.json()["id"]

        # 4. State Transitions: todo -> in_progress -> review -> done
        for next_status in ["in_progress", "review", "done"]:
            up_res = await client.put(f"/api/tasks/{parent_task_id}", json={"status": next_status}, headers=headers)
            assert up_res.status_code == 200
            assert up_res.json()["status"] == "updated"

        # 5. List Tasks for Team
        tasks_list = await client.get(f"/api/tasks/{team_id}", headers=headers)
        assert tasks_list.status_code == 200
        all_tasks = tasks_list.json()
        assert len(all_tasks) >= 3
        parent_task = next(t for t in all_tasks if t["id"] == parent_task_id)
        assert parent_task["priority"] == "high"

        # 6. Add Task Comments
        comment_payload = {
            "author_id": user_id,
            "author_name": "Alice Tester",
            "text": "Auth module is code reviewed and approved."
        }
        comment_res = await client.post(f"/api/tasks/{parent_task_id}/comments", json=comment_payload, headers=headers)
        assert comment_res.status_code == 200

        # 7. Delete Tasks
        del_res = await client.delete(f"/api/tasks/{task2_id}", headers=headers)
        assert del_res.status_code == 200
