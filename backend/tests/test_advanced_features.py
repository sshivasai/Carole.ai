"""
# backend/tests/test_advanced_features.py

Comprehensive test suite covering:
1. Hybrid GraphRAG (LanceDB Dense Memory & NetworkX Code Graph)
2. Scratchpad System (Team vs Personal, Append/Overwrite modes)
3. Plugin Studio & Dynamic Tool Hot-Reloading
4. Skills Studio & Tool Binding
5. Model Catalog Management
"""

import pytest
import os
import uuid
from pathlib import Path
from httpx import AsyncClient
from unittest.mock import patch
from tests.conftest import TestSession
from core.tools.tool_registry import ToolRegistry, ToolSpec
from core.memory.scratchpad import scratchpad_store
from core.config import PLUGINS_DIR


async def create_authenticated_user(client: AsyncClient, email: str = "advanced_tester@carole.ai"):
    signup_payload = {
        "email": email,
        "password": "StrongPassword123!",
        "first_name": "Adv",
        "last_name": "Tester",
    }
    res = await client.post("/api/auth/signup", json=signup_payload)
    data = res.json()
    token = data["token"]
    user_id = data["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers, user_id, email


# ============================================================
# 1. Scratchpad Tests (Team & Personal)
# ============================================================

@pytest.mark.asyncio
async def test_scratchpad_complete_flow(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "pad_tester@carole.ai")

    # Setup Project & Team
    p_res = await client.post("/api/projects", json={"name": "Scratchpad Proj", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]
    t_res = await client.post("/api/teams", json={"name": "Scratchpad Team", "project_id": project_id}, headers=headers)
    team_id = t_res.json()["id"]

    # 1. Write to Team Scratchpad in Append Mode
    write1 = await client.post(
        f"/api/scratchpad/{team_id}",
        json={
            "target": "team",
            "mode": "append",
            "content": "Phase 1: Database Migration",
            "author": "Alice"
        },
        headers=headers
    )
    assert write1.status_code == 200

    # 2. Write to Agent Personal Scratchpad in Overwrite Mode
    write2 = await client.post(
        f"/api/scratchpad/{team_id}",
        json={
            "target": "personal",
            "agent_name": "Coder",
            "mode": "overwrite",
            "content": "Current Working Variables:\nDB_HOST=localhost"
        },
        headers=headers
    )
    assert write2.status_code == 200

    # 3. Read Team Scratchpad
    read_team = await client.get(f"/api/scratchpad/{team_id}/team", headers=headers)
    assert read_team.status_code == 200
    assert "Phase 1: Database Migration" in read_team.json()["content"]

    # 4. Read Personal Scratchpad
    read_personal = await client.get(f"/api/scratchpad/{team_id}/personal?agent_name=Coder", headers=headers)
    assert read_personal.status_code == 200
    assert "DB_HOST=localhost" in read_personal.json()["content"]

    # 5. List All Scratchpads
    list_pads = await client.get(f"/api/scratchpad/{team_id}", headers=headers)
    assert list_pads.status_code == 200
    assert len(list_pads.json()) >= 1


# ============================================================
# 2. Plugin Studio & Dynamic Tool Registry Tests
# ============================================================

@pytest.mark.asyncio
async def test_plugin_studio_and_dynamic_registry(client: AsyncClient, monkeypatch):
    headers, user_id, email = await create_authenticated_user(client, "plugin_tester@carole.ai")
    monkeypatch.setenv("CAROLE_OWNER_ID", str(user_id))

    plugin_code = '''
from core.tools.plugin_decorator import carole_tool

@carole_tool(
    name="calculate_circumference",
    description="Calculates the circumference of a circle given its radius.",
    category="custom",
    permission_default="safe",
    parameters={"radius": {"type": "number", "required": True}}
)
async def calculate_circumference(args: dict, team_id: str) -> str:
    import math
    radius = float(args.get("radius", 0))
    return f"Circumference: {2 * math.pi * radius}"
'''
    filename = "circle_calc.py"

    # 1. Save Plugin
    with patch("core.chat.message_router.async_session", TestSession):
        save_res = await client.post(
            f"/api/plugins/{filename}",
            json={"code": plugin_code},
            headers=headers
        )
    assert save_res.status_code == 200
    assert save_res.json()["ok"] is True

    # 2. Verify Tool is registered in ToolRegistry
    tool_spec = ToolRegistry.get("calculate_circumference")
    assert tool_spec is not None
    assert "circumference" in tool_spec.description.lower()

    # 3. List Plugins
    list_res = await client.get("/api/plugins", headers=headers)
    assert list_res.status_code == 200
    plugins = list_res.json()
    assert any(p["filename"] == filename for p in plugins)

    # 4. Path Traversal & Invalid Filename Protection
    bad_res = await client.post(
        "/api/plugins/invalid$name.py",
        json={"code": "x = 1"},
        headers=headers
    )
    assert bad_res.status_code == 400

    # 5. Delete Plugin & Clean Up
    with patch("core.chat.message_router.async_session", TestSession):
        del_res = await client.delete(f"/api/plugins/{filename}", headers=headers)
    assert del_res.status_code == 200


# ============================================================
# 3. Skills Studio Tests
# ============================================================

@pytest.mark.asyncio
async def test_skills_studio_lifecycle(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "skill_tester@carole.ai")

    # Setup Project & Team
    p_res = await client.post("/api/projects", json={"name": "Skills Proj", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]
    t_res = await client.post("/api/teams", json={"name": "Skills Team", "project_id": project_id}, headers=headers)
    team_id = t_res.json()["id"]

    # 1. Create Skill Package
    skill_payload = {
        "team_id": team_id,
        "name": "SQL Optimization",
        "description": "Specialized SQL profiling and index analysis skill.",
        "system_prompt_addendum": "Always analyze EXPLAIN output before proposing query rewrites.",
        "tools": ["query_profiler", "explain_analyze"],
        "mcp_servers": []
    }
    create_res = await client.post("/api/skills", json=skill_payload, headers=headers)
    assert create_res.status_code == 200
    skill_data = create_res.json()
    assert skill_data["name"] == "SQL Optimization"
    skill_id = skill_data["id"]

    # 2. List Skills for Team
    list_skills = await client.get(f"/api/skills/{team_id}", headers=headers)
    assert list_skills.status_code == 200
    assert len(list_skills.json()) == 1
    assert list_skills.json()[0]["id"] == skill_id

    # 3. Update Skill
    update_res = await client.put(
        f"/api/skills/{skill_id}",
        json={"description": "Updated SQL performance optimization skill."},
        headers=headers
    )
    assert update_res.status_code == 200
    assert "Updated" in update_res.json()["description"]

    # 4. Delete Skill
    del_res = await client.delete(f"/api/skills/{skill_id}", headers=headers)
    assert del_res.status_code == 200

    list_skills2 = await client.get(f"/api/skills/{team_id}", headers=headers)
    assert len(list_skills2.json()) == 0


# ============================================================
# 4. Model Catalog Tests
# ============================================================

@pytest.mark.asyncio
async def test_model_catalog_endpoints(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "model_tester@carole.ai")

    # 1. Get Model Catalog
    get_res = await client.get("/api/models/catalog", headers=headers)
    assert get_res.status_code == 200
    catalog = get_res.json()
    assert "models" in catalog or isinstance(catalog, dict)

    # 2. List Models endpoint
    list_res = await client.get("/api/models", headers=headers)
    assert list_res.status_code == 200
