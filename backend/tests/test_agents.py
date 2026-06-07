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

    # Create project
    proj_payload = {"name": "Test Project", "owner_id": user_id}
    proj_res = await client.post("/api/projects", json=proj_payload)
    proj_id = proj_res.json()["id"]

    # Create team
    team_payload = {"name": "Test Team", "project_id": proj_id}
    team_res = await client.post("/api/teams", json=team_payload)
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
    res = await client.post("/api/agents", json=agent_payload)
    assert res.status_code == 200
    agent = res.json()
    assert agent["name"] == "Alex"
    assert agent["role"] == "Coder"
    assert agent["skills"] == ["file_write", "git_commit"]

    agent_id = agent["id"]

    # 3. List agents in team
    res = await client.get(f"/api/agents/{team_id}")
    assert res.status_code == 200
    agents = res.json()
    assert len(agents) == 1
    assert agents[0]["name"] == "Alex"

    # 4. Update agent config
    update_payload = {"name": "Alex Modified", "personality": "casual"}
    res = await client.put(f"/api/agents/{agent_id}", json=update_payload)
    assert res.status_code == 200

    # Fetch agents again to verify update
    res = await client.get(f"/api/agents/{team_id}")
    agents = res.json()
    assert agents[0]["name"] == "Alex Modified"

    # 5. Delete agent
    res = await client.delete(f"/api/agents/{agent_id}")
    assert res.status_code == 200

    # Ensure list is now empty
    res = await client.get(f"/api/agents/{team_id}")
    assert len(res.json()) == 0
