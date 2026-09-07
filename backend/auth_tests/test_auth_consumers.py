"""Execute real consumer functions without importing app/service initialization.

AST extraction preserves function bodies and line numbers; only route decorators
are removed. DB/auth are real; messaging, file access and shell launch are mocked.
This does not claim full application-import/startup integration coverage.
"""
import ast
import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock
import uuid

from fastapi import Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
import pytest
from sqlalchemy import delete, select

from core.auth.auth_middleware import require_auth
from core.auth.auth_service import auth_service
from core.memory.database import async_session
from core.memory.models import Project, Team, User

BACKEND = Path(__file__).resolve().parents[1]


def load_function(relative, name, **overrides):
    path = BACKEND / relative
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    node.decorator_list = []
    namespace = dict(
        asyncio=asyncio, json=json, logger=logging.getLogger("auth-consumer-test"),
        WebSocket=WebSocket, WebSocketDisconnect=WebSocketDisconnect, Query=Query,
        Optional=Optional, Header=Header, Depends=Depends, HTTPException=HTTPException,
        async_session=async_session, uuid=uuid, select=select, delete=delete, User=User,
        require_auth=require_auth,
    )
    namespace.update(overrides)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


@pytest.fixture
async def accounts(db):
    owner = User(email="owner@example.com", hashed_password="unused")
    other = User(email="other@example.com", hashed_password="unused")
    db.add_all([owner, other])
    await db.flush()
    project = Project(name="Owned", owner_id=owner.id)
    db.add(project)
    await db.flush()
    team = Team(name="Owned", project_id=project.id)
    db.add(team)
    await db.commit()
    return owner, other, project, team


def socket():
    ws = SimpleNamespace(accept=AsyncMock(), close=AsyncMock(), send_text=AsyncMock(), receive_text=AsyncMock(side_effect=WebSocketDisconnect()))
    return ws


@pytest.mark.parametrize("gateway", ["chat", "terminal", "notifications"])
@pytest.mark.parametrize("identity", ["valid", "malformed", "missing", "inactive", "deleted", "access_token"])
async def test_gateway_identity(gateway, identity, accounts, db):
    owner, _, project, team = accounts
    user_id = str(owner.id)
    ticket = auth_service.generate_ws_ticket(user_id)
    if identity == "malformed":
        ticket = "a.b.a"
    elif identity == "missing":
        ticket = ""
    elif identity == "access_token":
        ticket = auth_service._generate_token(owner)
    elif identity == "inactive":
        owner.is_active = False
        await db.commit()
    elif identity == "deleted":
        await db.execute(delete(Team))
        await db.execute(delete(Project))
        await db.delete(owner)
        await db.commit()
    ws = socket()
    bus = SimpleNamespace(
        subscribe_to_topics=AsyncMock(return_value=asyncio.Queue()),
        unsubscribe_from_topics=AsyncMock(), subscribe=AsyncMock(return_value=asyncio.Queue()),
        unsubscribe=AsyncMock(),
    )
    manager = SimpleNamespace(connect=AsyncMock())
    if gateway == "chat":
        fn = load_function("main.py", "websocket_endpoint", event_bus=bus, message_router=SimpleNamespace(route_message=AsyncMock()))
        await asyncio.wait_for(fn(ws, str(team.id), ticket), 5)
    elif gateway == "notifications":
        fn = load_function("main.py", "notifications_ws", event_bus=bus)
        await asyncio.wait_for(fn(ws, ticket), 5)
    else:
        fn = load_function("core/api/terminal_ws.py", "terminal_websocket", manager=manager)
        await fn(ws, str(project.id), ticket, "default")
    if identity == "valid":
        if gateway == "terminal":
            manager.connect.assert_awaited_once()
        else:
            ws.accept.assert_awaited_once()
        ws.close.assert_not_awaited()
    else:
        ws.close.assert_awaited_once_with(code=4001)
        ws.accept.assert_not_awaited()
        manager.connect.assert_not_awaited()
        bus.subscribe.assert_not_awaited()
        bus.subscribe_to_topics.assert_not_awaited()


@pytest.mark.parametrize("gateway", ["chat", "terminal"])
@pytest.mark.parametrize("resource", ["other_owner", "missing", "malformed"])
async def test_gateway_resource_ownership(gateway, resource, accounts):
    owner, other, project, team = accounts
    resource_id = str(team.id if gateway == "chat" else project.id)
    user = other if resource == "other_owner" else owner
    if resource == "missing":
        resource_id = str(uuid.uuid4())
    elif resource == "malformed":
        resource_id = "not-a-uuid"
    ws = socket()
    bus = SimpleNamespace(subscribe_to_topics=AsyncMock(return_value=asyncio.Queue()), unsubscribe_from_topics=AsyncMock())
    manager = SimpleNamespace(connect=AsyncMock())
    ticket = auth_service.generate_ws_ticket(str(user.id))
    if gateway == "chat":
        fn = load_function("main.py", "websocket_endpoint", event_bus=bus, message_router=SimpleNamespace(route_message=AsyncMock()))
        await asyncio.wait_for(fn(ws, resource_id, ticket), 5)
    else:
        fn = load_function("core/api/terminal_ws.py", "terminal_websocket", manager=manager)
        await fn(ws, resource_id, ticket, "default")
    ws.close.assert_awaited_once_with(code=4003)
    ws.accept.assert_not_awaited()
    manager.connect.assert_not_awaited()
    bus.subscribe_to_topics.assert_not_awaited()


@pytest.mark.parametrize("credential", ["ticket", "malformed", "inactive", "deleted"])
async def test_raw_file_auth_denies_before_file_access(credential, accounts, db):
    owner, _, _, _ = accounts
    token = auth_service._generate_token(owner)
    if credential == "ticket":
        token = auth_service.generate_ws_ticket(str(owner.id))
    elif credential == "malformed":
        token = "a.b.a"
    elif credential == "inactive":
        owner.is_active = False
        await db.commit()
    else:
        await db.execute(delete(Team))
        await db.execute(delete(Project))
        await db.delete(owner)
        await db.commit()
    file_tools = SimpleNamespace(_resolve_safe_path=AsyncMock(side_effect=AssertionError("Unauthenticated file access")))
    fn = load_function("core/api/file_routes.py", "get_raw_file", file_tools=file_tools)
    with pytest.raises(HTTPException) as exc:
        await fn(path="a.txt", project_id=None, token=token, authorization=None)
    assert exc.value.status_code == 401
    file_tools._resolve_safe_path.assert_not_awaited()


async def test_crud_ownership_and_self_deletion_contract(accounts, db):
    owner, other, project, team = accounts
    check = load_function("core/api/crud_routes.py", "_assert_team_access", Team=Team, Project=Project, AsyncSession=type(db))
    await check(db, str(team.id), str(owner.id))
    with pytest.raises(HTTPException) as exc:
        await check(db, str(team.id), str(other.id))
    assert exc.value.status_code == 403
    remove = load_function("core/api/crud_routes.py", "delete_user", AsyncSession=type(db), get_db=lambda: None)
    with pytest.raises(HTTPException) as exc:
        await remove(str(other.id), db, {"sub": str(owner.id)})
    assert exc.value.status_code == 403
    assert (await remove(str(other.id), db, {"sub": str(other.id)}))["status"] == "deleted"


@pytest.mark.parametrize("use_header", [False, True])
async def test_raw_file_valid_access_preserves_header_and_query(accounts, tmp_path, use_header):
    owner, _, project, _ = accounts
    token = auth_service._generate_token(owner)
    path = tmp_path / "file.txt"
    path.write_text("safe test content", encoding="utf-8")
    file_tools = SimpleNamespace(_resolve_safe_path=AsyncMock(return_value=path))
    from starlette.responses import FileResponse
    fn = load_function("core/api/file_routes.py", "get_raw_file", file_tools=file_tools, FileResponse=FileResponse)
    response = await fn(path="file.txt", project_id=str(project.id),
                        token="ignored" if use_header else token,
                        authorization=f"Bearer {token}" if use_header else None)
    assert response.path == path
    file_tools._resolve_safe_path.assert_awaited_once_with("file.txt", str(project.id))


async def test_existing_auth_lifecycle(client, monkeypatch):
    # Existing test assumes signup/login occur in the same second. Freeze only
    # this test's clock so its token-equality assertion is deterministic.
    import time
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    await load_function("tests/test_auth.py", "test_signup_login_lifecycle", AsyncClient=object)(client)


async def test_existing_auth_rate_limit(client):
    await load_function("tests/test_auth.py", "test_rate_limiting_enforced", AsyncClient=object, pytest=pytest)(client)


async def test_existing_ws_ticket_flow(client):
    helper = load_function("tests/test_ws_chat_flow.py", "create_authenticated_user", AsyncClient=object)
    fn = load_function("tests/test_ws_chat_flow.py", "test_ws_ticket_generation_and_verification",
                       AsyncClient=object, create_authenticated_user=helper, auth_service=auth_service)
    await fn(client)
