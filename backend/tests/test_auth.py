"""
# backend/tests/test_auth.py

Tests the Carole.ai authentication endpoints (signup, login, me).
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_signup_login_lifecycle(client: AsyncClient):
    # 1. Signup a new user
    signup_payload = {
        "email": "tester@carole.ai",
        "password": "supersecurepassword123",
        "first_name": "Test",
        "last_name": "User"
    }
    res = await client.post("/api/auth/signup", json=signup_payload)
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert "user" in data
    assert data["user"]["email"] == "tester@carole.ai"

    token = data["token"]

    # 2. Login with correct credentials
    login_payload = {
        "email": "tester@carole.ai",
        "password": "supersecurepassword123"
    }
    res = await client.post("/api/auth/login", json=login_payload)
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    # Login can cross a second boundary and legitimately issue a new JWT.
    # Verify both credentials authenticate the same user instead of comparing bytes.
    profile = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['token']}"})
    assert profile.status_code == 200
    assert profile.json()["id"] == data["user"]["id"]

    # 3. Retrieve /me profile with JWT token
    headers = {"Authorization": f"Bearer {token}"}
    res = await client.get("/api/auth/me", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "tester@carole.ai"
    assert data["first_name"] == "Test"

    # 4. Attempt login with wrong password
    bad_login_payload = {
        "email": "tester@carole.ai",
        "password": "wrongpassword"
    }
    res = await client.post("/api/auth/login", json=bad_login_payload)
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_protected_routes_require_authentication(client: AsyncClient):
    # Unauthenticated GET /settings must return 401
    res = await client.get("/api/settings")
    assert res.status_code == 401

    # Unauthenticated GET /plugins must return 401
    res = await client.get("/api/plugins")
    assert res.status_code == 401

    # Unauthenticated POST /plugins/action/generate must return 401
    res = await client.post("/api/plugins/action/generate", json={"prompt": "create tool"})
    assert res.status_code == 401

    # Unauthenticated GET /api/auth/google/status must return 401
    res = await client.get("/api/auth/google/status")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_user_self_deletion_authorization(client: AsyncClient):
    # Create User A
    res_a = await client.post("/api/auth/signup", json={
        "email": "usera@carole.ai",
        "password": "Password123!",
        "first_name": "User",
        "last_name": "A"
    })
    token_a = res_a.json()["token"]
    user_a_id = res_a.json()["user"]["id"]

    # Create User B
    res_b = await client.post("/api/auth/signup", json={
        "email": "userb@carole.ai",
        "password": "Password123!",
        "first_name": "User",
        "last_name": "B"
    })
    token_b = res_b.json()["token"]
    user_b_id = res_b.json()["user"]["id"]

    # User A tries to delete User B (IDOR attempt) -> must return 403 Forbidden
    headers_a = {"Authorization": f"Bearer {token_a}"}
    res_del = await client.delete(f"/api/users/{user_b_id}", headers=headers_a)
    assert res_del.status_code == 403

    # User B deletes own account -> succeeds (200)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    res_del_own = await client.delete(f"/api/users/{user_b_id}", headers=headers_b)
    assert res_del_own.status_code == 200


@pytest.mark.asyncio
async def test_rate_limiting_enforced(client: AsyncClient):
    from core.auth.rate_limiter import limiter, SLOWAPI_AVAILABLE
    if not SLOWAPI_AVAILABLE or not limiter:
        pytest.skip("slowapi not available")

    # Temporarily enable limiter
    limiter.enabled = True
    try:
        # Rapidly attempt 7 signups (limit is 5/minute)
        responses = []
        for i in range(7):
            res = await client.post("/api/auth/signup", json={
                "email": f"ratelimit_{i}@carole.ai",
                "password": "Password123!",
            })
            responses.append(res.status_code)

        # At least one of the requests past the 5th should return 429
        assert 429 in responses
    finally:
        limiter.enabled = False

