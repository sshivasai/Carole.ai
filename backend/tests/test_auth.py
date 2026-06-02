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
    assert data["token"] == token

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
