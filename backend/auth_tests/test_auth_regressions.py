"""Focused auth regressions; no application startup or external services."""
import asyncio
import hashlib
import hmac
import json
import threading
import time
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from core.auth import auth_service as service_module
from core.auth.auth_service import (
    _create_jwt, _decode_jwt, _hash_password, _verify_password, auth_service,
)
from core.auth.rate_limiter import limiter
from core.memory.database import async_session
from core.memory.models import User


async def signup(client, email="owner@example.com"):
    response = await client.post("/api/auth/signup", json={
        "email": email, "password": "password", "first_name": "Owner",
    })
    assert response.status_code == 200, response.text
    return response.json()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("token", ["a.b.a", "a.b.é", "a.b.!", "", "a.b", None, 123])
def test_malformed_tokens_fail_closed(token):
    assert _decode_jwt(token) is None


@pytest.mark.parametrize("payload", [
    [], [1], "text", 1, None,
    {"exp": "later"}, {"exp": 0}, {"exp": False}, {"exp": True},
    {"exp": float("nan")}, {"exp": float("inf")}, {},
    {"exp": time.time() + 100, "sub": 123},
    {"exp": time.time() + 100, "sub": "not-a-uuid"},
    {"exp": time.time() + 100, "sub": []},
])
def test_invalid_signed_claims_fail_closed(payload):
    if isinstance(payload, dict):
        payload = {"sub": str(uuid.uuid4()), **payload}
    assert _decode_jwt(_create_jwt(payload)) is None


def test_expiry_boundary_and_token_compatibility(monkeypatch):
    monkeypatch.setattr(service_module.time, "time", lambda: 1000)
    user = User(id=uuid.uuid4(), email="a@example.com")
    token = auth_service._generate_token(user)
    assert _decode_jwt(token)["sub"] == str(user.id)
    assert auth_service.verify_ws_ticket(token) is None
    ticket = auth_service.generate_ws_ticket(str(user.id))
    assert auth_service.verify_ws_ticket(ticket) == str(user.id)
    monkeypatch.setattr(service_module.time, "time", lambda: 1030)
    assert auth_service.verify_ws_ticket(ticket) is None


@pytest.mark.parametrize("stored", [None, "pbkdf2$broken", "pbkdf2$a$b", "pbkdf2$!!!!$!!!!", "salt$é", "plaintext"])
def test_corrupt_password_hash_rejected(stored):
    assert _verify_password("password", stored) is False


def test_password_hash_compatibility():
    current = _hash_password("pässword")
    assert _verify_password("pässword", current)
    assert not _verify_password("wrong", current)
    legacy = "abcd$" + hashlib.sha256("abcdpässword".encode()).hexdigest()
    assert _verify_password("pässword", legacy)
    assert not _verify_password("wrong", legacy)


async def test_http_lifecycle_and_ticket_purpose(client):
    data = await signup(client)
    headers = bearer(data["token"])
    login = await client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password"})
    assert login.status_code == 200
    assert _decode_jwt(login.json()["token"])["sub"] == data["user"]["id"]
    assert (await client.get("/api/auth/me", headers=headers)).json()["id"] == data["user"]["id"]
    assert (await client.get("/protected", headers=headers)).json()["sub"] == data["user"]["id"]
    ticket = (await client.post("/api/auth/ws-ticket", headers=headers)).json()["ticket"]
    assert auth_service.verify_ws_ticket(ticket) == data["user"]["id"]
    for path, method in [("/api/auth/me", "get"), ("/api/auth/ws-ticket", "post"), ("/protected", "get")]:
        assert (await getattr(client, method)(path, headers=bearer(ticket))).status_code == 401
    assert (await client.get("/optional", headers=bearer(ticket))).json() is None
    assert (await client.get("/optional")).json() is None
    for token in ["a.b.a", "", data["token"] + " trailing"]:
        assert (await client.get("/api/auth/me", headers=bearer(token))).status_code == 401


@pytest.mark.parametrize("state", ["inactive", "deleted"])
async def test_revoked_account_denied(client, db, state):
    data = await signup(client)
    user = await db.get(User, uuid.UUID(data["user"]["id"]))
    if state == "inactive":
        user.is_active = False
    else:
        await db.delete(user)
    await db.commit()
    headers = bearer(data["token"])
    for path, method in [("/api/auth/me", "get"), ("/api/auth/ws-ticket", "post"), ("/protected", "get")]:
        assert (await getattr(client, method)(path, headers=headers)).status_code == 401
    assert (await client.get("/optional", headers=headers)).json() is None
    assert (await client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password"})).status_code == 401


@pytest.mark.parametrize("field,value", [
    ("email", ""), ("email", "a" * 256), ("password", ""),
    ("first_name", "a" * 101), ("last_name", "a" * 101),
    ("email", []), ("password", None),
])
async def test_signup_input_limits(client, field, value):
    body = {"email": "a@example.com", "password": "password", field: value}
    assert (await client.post("/api/auth/signup", json=body)).status_code == 422


async def test_signup_preserves_case_and_password_whitespace(client):
    body = {"email": "Case@Example.com", "password": " ", "first_name": "a" * 100, "last_name": ""}
    assert (await client.post("/api/auth/signup", json=body)).status_code == 200
    assert (await client.post("/api/auth/login", json={"email": body["email"], "password": " "})).status_code == 200


async def test_duplicate_signup_race_recovers_session(monkeypatch):
    # Both requests observe no user before either inserts; use separate real sessions.
    original_hash = service_module._hash_password
    barrier = asyncio.Event()
    count = 0
    original_execute = service_module.AsyncSession.execute

    async def synchronized_execute(self, statement, *args, **kwargs):
        nonlocal count
        result = await original_execute(self, statement, *args, **kwargs)
        if statement.is_select and count < 2:
            count += 1
            if count == 2:
                barrier.set()
            await asyncio.wait_for(barrier.wait(), 5)
        return result

    monkeypatch.setattr(service_module.AsyncSession, "execute", synchronized_execute)

    async def attempt():
        async with async_session() as session:
            result = await auth_service.signup(session, "race@example.com", "password")
            await session.commit()
            assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
            return result

    results = await asyncio.gather(attempt(), attempt())
    assert sum("token" in r for r in results) == 1
    assert [r["error"] for r in results if "error" in r] == ["A user with this email already exists."]
    assert original_hash is service_module._hash_password


async def test_unrelated_integrity_error_not_reported_as_duplicate(db, monkeypatch):
    error = IntegrityError("insert", {}, Exception("unrelated constraint"))
    monkeypatch.setattr(db, "flush", AsyncMock(side_effect=error))
    with pytest.raises(IntegrityError):
        await auth_service.signup(db, "unique@example.com", "password")


async def test_legacy_upgrade_failure_rolls_back_and_login_succeeds(db, monkeypatch):
    legacy = "salt$" + hashlib.sha256(b"saltpassword").hexdigest()
    user = User(email="legacy@example.com", hashed_password=legacy, is_active=True)
    db.add(user)
    await db.commit()
    original_commit = db.commit
    original_rollback = db.rollback
    rollback = AsyncMock(wraps=original_rollback)
    monkeypatch.setattr(db, "rollback", rollback)
    async def fail_commit():
        # Trigger a real failed SQLAlchemy transaction, not merely an exception.
        db.add(User(email="legacy@example.com", hashed_password="unused"))
        await original_commit()

    monkeypatch.setattr(db, "commit", fail_commit)
    result = await auth_service.login(db, "legacy@example.com", "password")
    assert "token" in result
    rollback.assert_awaited_once()
    monkeypatch.setattr(db, "commit", original_commit)
    await db.refresh(user)
    assert user.hashed_password == legacy
    assert (await db.execute(text("SELECT 1"))).scalar_one() == 1


async def test_legacy_upgrade_success(db):
    user = User(email="legacy@example.com", hashed_password="salt$" + hashlib.sha256(b"saltpassword").hexdigest())
    db.add(user)
    await db.commit()
    assert "token" in await auth_service.login(db, user.email, "password")
    await db.refresh(user)
    assert user.hashed_password.startswith("pbkdf2$")


async def test_login_rate_limit_ip_spoofing_and_reset(client, monkeypatch):
    limiter.enabled = True
    responses = await asyncio.gather(*[
        client.post("/api/auth/login", json={"email": "absent@example.com", "password": "wrong"},
                    headers={"X-Forwarded-For": f"198.51.100.{i}"}) for i in range(14)
    ])
    assert sum(r.status_code == 401 for r in responses) == 10
    assert sum(r.status_code == 429 for r in responses) == 4
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + 61)
    response = await client.post("/api/auth/login", json={"email": "absent@example.com", "password": "wrong"})
    assert response.status_code == 401


async def test_signup_rate_limit(client):
    limiter.enabled = True
    statuses = []
    for i in range(7):
        response = await client.post("/api/auth/signup", json={"email": f"limit{i}@example.com", "password": "password"})
        statuses.append(response.status_code)
    assert statuses == [200] * 5 + [429] * 2


@pytest.mark.parametrize("header", [{"alg": "none"}, {"alg": "HS512"}, [], None])
def test_invalid_signed_jwt_header(header):
    h = service_module._b64url(json.dumps(header).encode())
    p = service_module._b64url(json.dumps({"sub": str(uuid.uuid4()), "exp": time.time() + 30}).encode())
    sig = hmac.new(service_module.JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    assert _decode_jwt(f"{h}.{p}.{service_module._b64url(sig)}") is None


async def test_password_work_does_not_block_event_loop(db, monkeypatch):
    loop_thread = threading.get_ident()
    original_hash = service_module._hash_password
    original_verify = service_module._verify_password
    calls = []

    def hash_off_loop(password):
        assert threading.get_ident() != loop_thread
        calls.append("hash")
        return original_hash(password)

    def verify_off_loop(password, stored):
        assert threading.get_ident() != loop_thread
        calls.append("verify")
        return original_verify(password, stored)

    monkeypatch.setattr(service_module, "_hash_password", hash_off_loop)
    monkeypatch.setattr(service_module, "_verify_password", verify_off_loop)
    assert "token" in await auth_service.signup(db, "thread@example.com", "password")
    await db.commit()
    assert "token" in await auth_service.login(db, "thread@example.com", "password")
    assert "error" in await auth_service.login(db, "missing@example.com", "password")
    assert calls == ["hash", "verify", "verify"]


async def test_missing_and_corrupt_passwords_return_login_error(db):
    user = User(email="broken@example.com", hashed_password="pbkdf2$broken")
    db.add(user)
    await db.commit()
    assert await auth_service.login(db, user.email, "password") == {"error": "Invalid email or password."}
    assert await auth_service.login(db, "absent@example.com", "password") == {"error": "Invalid email or password."}


def test_production_secret_guard(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    for secret in [None, service_module._DEFAULT_DEV_SECRET]:
        if secret is None:
            monkeypatch.delenv("JWT_SECRET")
        else:
            monkeypatch.setenv("JWT_SECRET", secret)
        with pytest.raises(RuntimeError):
            service_module.validate_auth_config()
    monkeypatch.setenv("JWT_SECRET", "non-default-test-secret")
    service_module.validate_auth_config()
