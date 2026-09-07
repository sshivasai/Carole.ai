"""Comprehensive Authorization Boundaries & Resource Ownership Tests.

Run via:
    python -m pytest --confcutdir=backend/auth_tests backend/auth_tests/test_authorization_boundaries.py

Validates:
1. Unauthenticated requests (no token) -> 401 Unauthorized across all sensitive routes.
2. Cross-tenant access (User B attempting to read, update, delete, or invoke User A's resources) -> 403 Forbidden.
3. Malformed UUIDs -> 400 Bad Request.
4. Non-existent resources -> 404 Not Found.
5. Resource owner requests (User A accessing User A's resources) -> 200 / 201 Success.
6. Non-mutation verification -> Denied requests produce zero side-effects in the database.
"""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from core.api.crud_routes import router as crud_router
from core.api.file_routes import router as file_router
from core.api.git_routes import router as git_router
from core.api.observability_routes import router as observability_router
from core.api.scratchpad_routes import router as scratchpad_router
from core.api.search_routes import router as search_router
from core.api.skill_routes import router as skill_router
from core.api.terminal_routes import router as terminal_router
from core.auth.auth_service import auth_service
from core.memory.database import async_session
from core.memory.models import (
    Agent,
    FileBackup,
    McpServer,
    Message,
    Project,
    Skill,
    Task,
    Team,
    User,
)


@pytest.fixture
def auth_app():
    app = FastAPI()
    app.include_router(crud_router)
    app.include_router(file_router)
    app.include_router(git_router)
    app.include_router(scratchpad_router)
    app.include_router(skill_router, prefix="/api/skills", tags=["skills"])
    app.include_router(terminal_router)
    app.include_router(search_router)
    app.include_router(observability_router)
    return app


@pytest.fixture
async def api_client(auth_app):
    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
async def setup_resources(db):
    """Creates User A (owner) and User B (attacker/stranger) with an entity hierarchy."""
    user_a = User(
        email="owner_a@example.com",
        hashed_password="unused_hashed_pwd",
        first_name="Alice",
        is_active=True,
    )
    user_b = User(
        email="stranger_b@example.com",
        hashed_password="unused_hashed_pwd",
        first_name="Bob",
        is_active=True,
    )
    db.add_all([user_a, user_b])
    await db.flush()

    token_a = auth_service._generate_token(user_a)
    token_b = auth_service._generate_token(user_b)

    # User A's Project -> Team -> Agent / Task / Message / Skill / McpServer / FileBackup
    project_a = Project(name="Project Alpha", owner_id=user_a.id)
    db.add(project_a)
    await db.flush()

    team_a = Team(name="Alpha Team", project_id=project_a.id)
    db.add(team_a)
    await db.flush()

    agent_a = Agent(
        name="CoderAgent",
        role="Coder",
        model="test-model",
        system_prompt="You are a helpful coding assistant.",
        team_id=team_a.id,
    )
    db.add(agent_a)
    await db.flush()

    task_a = Task(
        team_id=team_a.id,
        title="Initial Task",
        description="Task for Alpha Team",
        implementation_plan="Original Plan Content",
        todo_list=[{"task": "Step 1", "done": False}],
    )
    db.add(task_a)
    await db.flush()

    message_a = Message(
        team_id=team_a.id,
        sender_id="human",
        sender_name="Alice",
        text="Hello Alpha Team",
        is_intermediate=False,
        is_private=False,
    )
    db.add(message_a)
    await db.flush()

    skill_a = Skill(
        team_id=team_a.id,
        name="DataParser",
        description="Parses CSV/JSON",
    )
    db.add(skill_a)
    await db.flush()

    mcp_a = McpServer(
        team_id=team_a.id,
        server_name="sqlite-mcp",
        command="npx",
        args=["-y", "sqlite-mcp"],
    )
    db.add(mcp_a)
    await db.flush()

    file_backup_a = FileBackup(
        team_id=team_a.id,
        file_path="main.py",
        operation="write",
    )
    db.add(file_backup_a)
    await db.commit()

    return {
        "user_a": user_a,
        "user_b": user_b,
        "token_a": token_a,
        "token_b": token_b,
        "headers_a": {"Authorization": f"Bearer {token_a}"},
        "headers_b": {"Authorization": f"Bearer {token_b}"},
        "project_a": project_a,
        "team_a": team_a,
        "agent_a": agent_a,
        "task_a": task_a,
        "message_a": message_a,
        "skill_a": skill_a,
        "mcp_a": mcp_a,
        "file_backup_a": file_backup_a,
    }


# =========================================================================
# 1. Unauthenticated Rejection Tests (401 Unauthorized)
# =========================================================================

@pytest.mark.parametrize(
    "method,endpoint,json_payload",
    [
        ("post", "/api/agents", {"name": "NewAgent", "role": "Dev", "model": "gpt-4"}),
        ("get", "/api/scratchpad/00000000-0000-0000-0000-000000000000", None),
        ("get", "/api/scratchpad/00000000-0000-0000-0000-000000000000/team", None),
        ("post", "/api/scratchpad/00000000-0000-0000-0000-000000000000", {"content": "text"}),
        ("put", "/api/scratchpad/00000000-0000-0000-0000-000000000000", {"content": "text"}),
        ("delete", "/api/scratchpad/00000000-0000-0000-0000-000000000000", None),
        ("get", "/api/observability/traces", None),
        ("get", "/api/observability/stats", None),
        ("post", "/api/observability/clear", None),
        ("post", "/api/observability/emit-sample", None),
        ("get", "/api/skills/00000000-0000-0000-0000-000000000000", None),
        ("post", "/api/skills", {"team_id": "00000000-0000-0000-0000-000000000000", "name": "S"}),
        ("put", "/api/skills/00000000-0000-0000-0000-000000000000", {"name": "S2"}),
        ("delete", "/api/skills/00000000-0000-0000-0000-000000000000", None),
        ("post", "/api/terminal/execute", {"command": "dir"}),
        ("get", "/api/search/grep?q=hello", None),
    ],
)
async def test_unauthenticated_requests_fail_with_401(api_client, method, endpoint, json_payload):
    if json_payload is not None:
        resp = await api_client.request(method.upper(), endpoint, json=json_payload)
    else:
        resp = await api_client.request(method.upper(), endpoint)
    assert resp.status_code == 401, f"Expected 401 for unauthenticated {method.upper()} {endpoint}, got {resp.status_code}: {resp.text}"


# =========================================================================
# 2. Cross-Tenant Authorization Boundary Tests (403 Forbidden)
# =========================================================================

async def test_cross_tenant_project_access_denied(api_client, setup_resources):
    res = setup_resources
    headers_b = res["headers_b"]
    p_id = str(res["project_a"].id)

    # User B cannot read User A's project
    resp = await api_client.get(f"/api/projects/single/{p_id}", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot update User A's project
    resp = await api_client.put(f"/api/projects/{p_id}", json={"name": "Hacked"}, headers=headers_b)
    assert resp.status_code == 403

    # User B cannot delete User A's project
    resp = await api_client.delete(f"/api/projects/{p_id}", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot clear User A's project memory
    resp = await api_client.delete(f"/api/projects/{p_id}/memory", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot view User A's project usage
    resp = await api_client.get(f"/api/usage/{p_id}", headers=headers_b)
    assert resp.status_code == 403


async def test_cross_tenant_team_access_denied(api_client, setup_resources):
    res = setup_resources
    headers_b = res["headers_b"]
    p_id = str(res["project_a"].id)
    t_id = str(res["team_a"].id)

    # User B cannot create team in User A's project
    resp = await api_client.post("/api/teams", json={"name": "B Team", "project_id": p_id}, headers=headers_b)
    assert resp.status_code == 403

    # User B cannot list teams in User A's project
    resp = await api_client.get(f"/api/teams/{p_id}", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot read User A's team
    resp = await api_client.get(f"/api/teams/single/{t_id}", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot delete User A's team
    resp = await api_client.delete(f"/api/teams/{t_id}", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot clear chat in User A's team
    resp = await api_client.delete(f"/api/teams/{t_id}/messages", headers=headers_b)
    assert resp.status_code == 403


async def test_cross_tenant_agent_access_denied(api_client, setup_resources):
    res = setup_resources
    headers_b = res["headers_b"]
    t_id = str(res["team_a"].id)
    a_id = str(res["agent_a"].id)

    # User B cannot create agent in User A's team
    resp = await api_client.post("/api/agents", json={"name": "Spy", "role": "Dev", "model": "m", "team_id": t_id}, headers=headers_b)
    assert resp.status_code == 403

    # User B cannot list agents in User A's team
    resp = await api_client.get(f"/api/agents/{t_id}", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot update User A's agent
    resp = await api_client.put(f"/api/agents/{a_id}", json={"name": "Modified"}, headers=headers_b)
    assert resp.status_code == 403

    # User B cannot stop User A's agent
    resp = await api_client.post(f"/api/agents/{a_id}/stop", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot inspect User A's agent queue
    resp = await api_client.get(f"/api/agents/{a_id}/queue", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot clone User A's agent
    resp = await api_client.post(f"/api/agents/{a_id}/clone", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot delete User A's agent
    resp = await api_client.delete(f"/api/agents/{a_id}", headers=headers_b)
    assert resp.status_code == 403


async def test_cross_tenant_task_and_plan_access_denied(api_client, setup_resources):
    res = setup_resources
    headers_b = res["headers_b"]
    t_id = str(res["team_a"].id)
    task_id = str(res["task_a"].id)

    # User B cannot create task in User A's team
    resp = await api_client.post("/api/tasks", json={"team_id": t_id, "title": "B Task"}, headers=headers_b)
    assert resp.status_code == 403

    # User B cannot list tasks in User A's team
    resp = await api_client.get(f"/api/tasks/{t_id}", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot update User A's task
    resp = await api_client.put(f"/api/tasks/{task_id}", json={"title": "Altered"}, headers=headers_b)
    assert resp.status_code == 403

    # User B cannot read User A's task plan
    resp = await api_client.get(f"/api/tasks/{task_id}/plan", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot approve User A's task plan
    resp = await api_client.post(f"/api/tasks/{task_id}/plan/approve", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot reject User A's task plan
    resp = await api_client.post(f"/api/tasks/{task_id}/plan/reject", json={"feedback": "Nope"}, headers=headers_b)
    assert resp.status_code == 403

    # User B cannot comment on User A's task plan
    resp = await api_client.post(f"/api/tasks/{task_id}/plan/comment", json={"line_index": 0, "text": "Bad plan"}, headers=headers_b)
    assert resp.status_code == 403

    # User B cannot patch User A's task plan text
    resp = await api_client.patch(f"/api/tasks/{task_id}/plan", json={"plan_markdown": "Hijacked plan"}, headers=headers_b)
    assert resp.status_code == 403

    # User B cannot patch User A's task todos
    resp = await api_client.patch(f"/api/tasks/{task_id}/todos", json={"todos": []}, headers=headers_b)
    assert resp.status_code == 403

    # User B cannot delete User A's task
    resp = await api_client.delete(f"/api/tasks/{task_id}", headers=headers_b)
    assert resp.status_code == 403


async def test_cross_tenant_message_access_denied(api_client, setup_resources):
    res = setup_resources
    headers_b = res["headers_b"]
    msg_id = str(res["message_a"].id)

    # User B cannot edit User A's message
    resp = await api_client.put(f"/api/messages/{msg_id}", json={"text": "Defaced"}, headers=headers_b)
    assert resp.status_code == 403

    # User B cannot rollback User A's message
    resp = await api_client.delete(f"/api/messages/{msg_id}/rollback", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot delete User A's message
    resp = await api_client.delete(f"/api/messages/{msg_id}", headers=headers_b)
    assert resp.status_code == 403


async def test_cross_tenant_scratchpad_access_denied(api_client, setup_resources):
    res = setup_resources
    headers_b = res["headers_b"]
    t_id = str(res["team_a"].id)

    # User B cannot list User A's scratchpads
    resp = await api_client.get(f"/api/scratchpad/{t_id}", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot read User A's scratchpad
    resp = await api_client.get(f"/api/scratchpad/{t_id}/team", headers=headers_b)
    assert resp.status_code == 403

    # User B cannot append to User A's scratchpad
    resp = await api_client.post(f"/api/scratchpad/{t_id}", json={"content": "Malicious append", "target": "team"}, headers=headers_b)
    assert resp.status_code == 403

    # User B cannot overwrite User A's scratchpad
    resp = await api_client.put(f"/api/scratchpad/{t_id}", json={"content": "Malicious overwrite", "target": "team"}, headers=headers_b)
    assert resp.status_code == 403

    # User B cannot delete User A's scratchpad
    resp = await api_client.delete(f"/api/scratchpad/{t_id}?target=team", headers=headers_b)
    assert resp.status_code == 403


async def test_cross_tenant_skill_and_mcp_access_denied(api_client, setup_resources):
    res = setup_resources
    headers_b = res["headers_b"]
    t_id = str(res["team_a"].id)
    s_id = str(res["skill_a"].id)
    mcp_id = str(res["mcp_a"].id)

    # Skills
    resp = await api_client.get(f"/api/skills/{t_id}", headers=headers_b)
    assert resp.status_code == 403

    resp = await api_client.post("/api/skills", json={"team_id": t_id, "name": "HackerSkill"}, headers=headers_b)
    assert resp.status_code == 403

    resp = await api_client.put(f"/api/skills/{s_id}", json={"name": "Renamed"}, headers=headers_b)
    assert resp.status_code == 403

    resp = await api_client.delete(f"/api/skills/{s_id}", headers=headers_b)
    assert resp.status_code == 403

    # MCP servers
    resp = await api_client.get(f"/api/mcp/{t_id}", headers=headers_b)
    assert resp.status_code == 403

    resp = await api_client.post("/api/mcp", json={"team_id": t_id, "server_name": "bad-mcp", "command": "cmd"}, headers=headers_b)
    assert resp.status_code == 403

    resp = await api_client.delete(f"/api/mcp/{mcp_id}", headers=headers_b)
    assert resp.status_code == 403


async def test_cross_tenant_file_and_terminal_access_denied(api_client, setup_resources):
    res = setup_resources
    headers_b = res["headers_b"]
    p_id = str(res["project_a"].id)
    t_id = str(res["team_a"].id)

    # File routes with project_id
    resp = await api_client.get(f"/api/files/list?project_id={p_id}", headers=headers_b)
    assert resp.status_code == 403

    resp = await api_client.post("/api/files/write", json={"path": "secret.txt", "content": "data", "project_id": p_id}, headers=headers_b)
    assert resp.status_code == 403

    resp = await api_client.delete(f"/api/files/delete?path=secret.txt&project_id={p_id}", headers=headers_b)
    assert resp.status_code == 403

    resp = await api_client.get(f"/api/files/logs/{t_id}", headers=headers_b)
    assert resp.status_code == 403

    # Git routes with project_id
    resp = await api_client.get(f"/api/git/status?project_id={p_id}", headers=headers_b)
    assert resp.status_code == 403

    # Terminal route with project_id
    resp = await api_client.post("/api/terminal/execute", json={"command": "dir", "project_id": p_id}, headers=headers_b)
    assert resp.status_code == 403

    # Search route with project_id
    resp = await api_client.get(f"/api/search/grep?q=password&project_id={p_id}", headers=headers_b)
    assert resp.status_code == 403


# =========================================================================
# 3. Input Validation: Malformed UUIDs (400) & Missing Resources (404)
# =========================================================================

async def test_malformed_and_missing_resource_ids(api_client, setup_resources):
    headers_a = setup_resources["headers_a"]
    bad_id = "not-a-valid-uuid"
    missing_id = str(uuid.uuid4())

    # 400 on malformed UUID
    resp = await api_client.get(f"/api/projects/single/{bad_id}", headers=headers_a)
    assert resp.status_code == 400

    resp = await api_client.get(f"/api/teams/single/{bad_id}", headers=headers_a)
    assert resp.status_code == 400

    resp = await api_client.put(f"/api/tasks/{bad_id}", json={"title": "X"}, headers=headers_a)
    assert resp.status_code == 400

    # 404 on non-existent UUID
    resp = await api_client.get(f"/api/projects/single/{missing_id}", headers=headers_a)
    assert resp.status_code == 404

    resp = await api_client.get(f"/api/teams/single/{missing_id}", headers=headers_a)
    assert resp.status_code == 404

    resp = await api_client.put(f"/api/tasks/{missing_id}", json={"title": "X"}, headers=headers_a)
    assert resp.status_code == 404


# =========================================================================
# 4. Authorized Success Tests (200 / 201) & Non-Mutation Assertions
# =========================================================================

async def test_owner_access_granted_and_non_mutation_verified(api_client, setup_resources, db):
    res = setup_resources
    headers_a = res["headers_a"]
    headers_b = res["headers_b"]
    p_id = str(res["project_a"].id)
    t_id = str(res["team_a"].id)
    task_id = str(res["task_a"].id)

    # 1. User B attempts unauthorized mutation on Task A
    resp_denied = await api_client.put(
        f"/api/tasks/{task_id}",
        json={"title": "Tampered Title by User B"},
        headers=headers_b,
    )
    assert resp_denied.status_code == 403

    # Verify Non-Mutation in DB: Title MUST remain "Initial Task"
    task_db = (await db.execute(select(Task).where(Task.id == res["task_a"].id))).scalar_one()
    assert task_db.title == "Initial Task", "Security breach: User B mutated User A's task title despite 403!"

    # 2. User A successfully updates their own task
    resp_owner = await api_client.put(
        f"/api/tasks/{task_id}",
        json={"title": "Legitimately Updated by User A"},
        headers=headers_a,
    )
    assert resp_owner.status_code == 200

    # Verify Mutation in DB by authorized owner
    await db.refresh(task_db)
    assert task_db.title == "Legitimately Updated by User A"

    # 3. User A can read project, team, and task plan
    resp_proj = await api_client.get(f"/api/projects/single/{p_id}", headers=headers_a)
    assert resp_proj.status_code == 200
    assert resp_proj.json()["id"] == p_id

    resp_team = await api_client.get(f"/api/teams/single/{t_id}", headers=headers_a)
    assert resp_team.status_code == 200
    assert resp_team.json()["id"] == t_id

    resp_plan = await api_client.get(f"/api/tasks/{task_id}/plan", headers=headers_a)
    assert resp_plan.status_code == 200
    assert resp_plan.json()["implementation_plan"] == "Original Plan Content"
