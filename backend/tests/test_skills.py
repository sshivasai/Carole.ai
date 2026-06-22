import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_skills_crud_and_activation(client: AsyncClient):
    # 1. Signup user
    signup_payload = {
        "email": "skills.owner@carole.ai",
        "password": "supersecurepassword123"
    }
    signup_res = await client.post("/api/auth/signup", json=signup_payload)
    assert signup_res.status_code == 200, f"Signup failed: {signup_res.text}"
    user_id = signup_res.json()["user"]["id"]
    token = signup_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create a project + team to scope skills under (skills are team-scoped)
    proj_res = await client.post(
        "/api/projects", json={"name": "Skills Project", "owner_id": user_id}, headers=headers
    )
    assert proj_res.status_code == 200, proj_res.text
    project_id = proj_res.json()["id"]

    team_res = await client.post(
        "/api/teams", json={"name": "Skills Team", "project_id": project_id}, headers=headers
    )
    assert team_res.status_code == 200, team_res.text
    team_id = team_res.json()["id"]

    # 3. List skills for the team (should start empty)
    res = await client.get(f"/api/skills/{team_id}", headers=headers)
    assert res.status_code == 200, res.text
    skills = res.json()
    assert isinstance(skills, list)
    assert skills == []

    # 4. Create a custom skill
    skill_payload = {
        "team_id": team_id,
        "name": "Custom Greeter",
        "description": "Greets the user in a specific way",
        "system_prompt_addendum": "You always greet the user with 'Howdy partner!'.",
        "tools": ["web_search"],
        "mcp_servers": [],
    }
    res = await client.post("/api/skills", json=skill_payload, headers=headers)
    assert res.status_code == 200, res.text
    new_skill = res.json()
    assert new_skill["name"] == "Custom Greeter"
    assert new_skill["is_active"] is True
    assert new_skill["tools"] == ["web_search"]
    skill_id = new_skill["id"]

    # 5. Deactivate the skill via update
    res = await client.put(
        f"/api/skills/{skill_id}", json={"is_active": False}, headers=headers
    )
    assert res.status_code == 200, res.text
    assert res.json()["is_active"] is False

    # 6. Listing active-only skills should now exclude it
    res = await client.get(f"/api/skills/{team_id}?active_only=true", headers=headers)
    assert res.status_code == 200, res.text
    active_skills = res.json()
    assert not any(s["id"] == skill_id for s in active_skills)

    # But it is still present in the full (non-filtered) listing
    res = await client.get(f"/api/skills/{team_id}", headers=headers)
    assert res.status_code == 200, res.text
    assert any(s["id"] == skill_id for s in res.json())

    # 7. Delete the skill
    res = await client.delete(f"/api/skills/{skill_id}", headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "ok"

    # 8. Confirm deletion
    res = await client.get(f"/api/skills/{team_id}", headers=headers)
    assert res.status_code == 200, res.text
    assert not any(s["id"] == skill_id for s in res.json())
