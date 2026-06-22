import pytest
from httpx import AsyncClient
from uuid import uuid4

@pytest.mark.asyncio
async def test_cost_management_stats(client: AsyncClient):
    # 1. Signup a user and create a project/team
    signup_payload = {
        "email": "cost.owner@carole.ai",
        "password": "supersecurepassword123"
    }
    signup_res = await client.post("/api/auth/signup", json=signup_payload)
    assert signup_res.status_code == 200, f"Signup failed: {signup_res.text}"
    user_id = signup_res.json()["user"]["id"]
    token = signup_res.json()["token"]

    headers = {"Authorization": f"Bearer {token}"}

    # Create project
    proj_payload = {"name": "Cost Project", "owner_id": user_id}
    proj_res = await client.post("/api/projects", json=proj_payload, headers=headers)
    assert proj_res.status_code == 200
    proj_id = proj_res.json()["id"]

    # 2. Get cost stats (should be 0)
    res = await client.get(f"/api/cost/stats?project_id={proj_id}", headers=headers)
    assert res.status_code == 200
    stats = res.json()
    assert stats["total_spend_usd"] == 0.0
    assert stats["total_prompt_tokens"] == 0
    assert stats["total_completion_tokens"] == 0
    assert stats["total_tokens"] == 0

    # 3. Update budget limit
    budget_payload = {"project_id": proj_id, "budget_limit_usd": 150.50}
    res = await client.post("/api/cost/budget", json=budget_payload, headers=headers)
    assert res.status_code == 200
    assert res.json()["budget_limit_usd"] == "150.5"

    # 4. Get cost stats again
    res = await client.get(f"/api/cost/stats?project_id={proj_id}", headers=headers)
    assert res.status_code == 200
    stats = res.json()
    assert stats["budget_limit_usd"] == 150.5
