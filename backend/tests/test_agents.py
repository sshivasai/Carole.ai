"""
# backend/tests/test_agents.py

Tests agent configuration, templates, and creation endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_role_templates(client: AsyncClient):
    # 1. Fetch list of role templates
    res = await client.get("/api/role-templates")
    assert res.status_code == 200
    templates = res.json()
    assert len(templates) > 0
    assert "Coordinator" in [t["role"] for t in templates]

    # 2. Get specific template details
    res = await client.get("/api/role-templates/Coder")
    assert res.status_code == 200
    template = res.json()
    assert "claude-sonnet-4" in template["recommended_model"] or "gpt-4o" in template["recommended_model"] or "openrouter/free" in template["recommended_model"]
    assert "skills" in template


@pytest.mark.asyncio
async def test_agent_creation_and_crud(client: AsyncClient):
    # 1. Signup a user and create a project/team
    signup_payload = {
        "email": "agent.owner@carole.ai",
        "password": "supersecurepassword123"
    }
    signup_res = await client.post("/api/auth/signup", json=signup_payload)
    user_id = signup_res.json()["user"]["id"]
    token = signup_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create project
    proj_payload = {"name": "Test Project", "owner_id": user_id}
    proj_res = await client.post("/api/projects", json=proj_payload, headers=headers)
    proj_id = proj_res.json()["id"]

    # Create team
    team_payload = {"name": "Test Team", "project_id": proj_id}
    team_res = await client.post("/api/teams", json=team_payload, headers=headers)
    team_id = team_res.json()["id"]

    # 2. Create an Agent scoped to the Team
    agent_payload = {
        "team_id": team_id,
        "name": "Alex",
        "role": "Coder",
        "model": "gpt-4o-mini",
        "system_prompt": "You are Alex the Coder.",
        "personality": "witty",
        "custom_instructions": "Make it dry.",
        "skills": ["file_write", "git_commit"],
        "tool_permissions": {"file_write": "safe"}
    }
    res = await client.post("/api/agents", json=agent_payload, headers=headers)
    assert res.status_code == 200
    agent = res.json()
    assert agent["name"] == "Alex"
    assert agent["role"] == "Coder"
    assert agent["skills"] == ["file_write", "git_commit"]

    agent_id = agent["id"]

    # 3. List agents in team
    res = await client.get(f"/api/agents/{team_id}", headers=headers)
    assert res.status_code == 200
    agents = res.json()
    assert len(agents) == 1
    assert agents[0]["name"] == "Alex"

    # 4. Update agent config
    update_payload = {"name": "Alex Modified", "personality": "casual"}
    res = await client.put(f"/api/agents/{agent_id}", json=update_payload, headers=headers)
    assert res.status_code == 200

    # Fetch agents again to verify update
    res = await client.get(f"/api/agents/{team_id}", headers=headers)
    agents = res.json()
    assert agents[0]["name"] == "Alex Modified"

    # 5. Delete agent
    res = await client.delete(f"/api/agents/{agent_id}", headers=headers)
    assert res.status_code == 200

    # Ensure list is now empty
    res = await client.get(f"/api/agents/{team_id}", headers=headers)
    assert len(res.json()) == 0


@pytest.mark.asyncio
async def test_create_team_agent_tool(client: AsyncClient):
    signup_payload = {
        "email": "tool.agent.owner@carole.ai",
        "password": "supersecurepassword123"
    }
    signup_res = await client.post("/api/auth/signup", json=signup_payload)
    user_id = signup_res.json()["user"]["id"]
    token = signup_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create project & team
    proj_res = await client.post("/api/projects", json={"name": "Tool Proj", "owner_id": user_id}, headers=headers)
    proj_id = proj_res.json()["id"]
    team_res = await client.post("/api/teams", json={"name": "Tool Team", "project_id": proj_id}, headers=headers)
    team_id = team_res.json()["id"]

    from unittest.mock import patch
    from tests.conftest import TestSession
    from core.tools.tool_executor import ToolExecutor

    with patch("core.tools.agent_tools.async_session", TestSession), \
         patch("core.memory.database.async_session", TestSession), \
         patch("core.chat.message_router.async_session", TestSession):
        executor = ToolExecutor()
        result = await executor.execute(
            tool_name="create_team_agent",
            arguments={
                "name": "Jordan",
                "role": "Software Engineer",
                "expertise": "Full-stack Python, React, and system architecture"
            },
            agent_id="test-agent",
            agent_name="Archer",
            team_id=team_id,
            permissions={"subagents": "allow"}
        )

        assert "Successfully added permanent teammate '@Jordan'" in result

    # Verify agent is permanently listed in the team
    agents_res = await client.get(f"/api/agents/{team_id}", headers=headers)
    assert agents_res.status_code == 200
    agents = agents_res.json()
    assert len(agents) == 1
    assert agents[0]["name"] == "Jordan"
    assert agents[0]["role"] == "Software Engineer"

    # Test update_team_agent tool
    with patch("core.tools.agent_tools.async_session", TestSession), \
         patch("core.memory.database.async_session", TestSession), \
         patch("core.chat.message_router.async_session", TestSession):
        update_result = await executor.execute(
            tool_name="update_team_agent",
            arguments={
                "name_or_id": "Jordan",
                "role": "Principal Software Engineer",
                "model": "anthropic/claude-3.5-sonnet"
            },
            agent_id="test-agent",
            agent_name="Archer",
            team_id=team_id,
            permissions={"subagents": "allow"}
        )
        assert "Successfully updated teammate '@Jordan'" in update_result
        assert "Principal Software Engineer" in update_result

    # Verify agent is updated in DB
    agents_res = await client.get(f"/api/agents/{team_id}", headers=headers)
    assert agents_res.status_code == 200
    agents = agents_res.json()
    assert agents[0]["role"] == "Principal Software Engineer"
    assert agents[0]["model"] == "anthropic/claude-3.5-sonnet"

    # Test delete_team_agent tool
    with patch("core.tools.agent_tools.async_session", TestSession), \
         patch("core.memory.database.async_session", TestSession), \
         patch("core.chat.message_router.async_session", TestSession):
        delete_result = await executor.execute(
            tool_name="delete_team_agent",
            arguments={"name_or_id": "Jordan"},
            agent_id="test-agent",
            agent_name="Archer",
            team_id=team_id,
            permissions={"subagents": "allow"}
        )
        assert "Successfully removed '@Jordan'" in delete_result

    # Verify agent is gone from DB
    agents_res = await client.get(f"/api/agents/{team_id}", headers=headers)
    assert agents_res.status_code == 200
    agents = agents_res.json()
    assert len(agents) == 0


