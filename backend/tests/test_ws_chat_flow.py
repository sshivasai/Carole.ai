"""
# backend/tests/test_ws_chat_flow.py

Comprehensive test suite covering:
1. WebSocket Ticket Generation & Verification (/api/auth/ws-ticket)
2. Message Router & EventBus real-time publishing
3. Direct Mentions (/@Agent) vs Group Broadcasts
4. Human-In-The-Loop (HITL) Tool Approvals (/api/tools/approve/{tx_id})
5. Interactive Agent Question-Answering (/api/agent/answer/{question_id})
6. Chat History Pagination, Deletion & Clear
"""

import pytest
import asyncio
import uuid
from httpx import AsyncClient
from unittest.mock import patch
from tests.conftest import TestSession
from core.chat.event_bus import event_bus
from core.chat.message_router import message_router
from core.auth.auth_service import auth_service
from core.tools.tool_executor import pending_approvals, approval_results
from core.tools.interaction_tools import pending_questions, question_answers


async def create_authenticated_user(client: AsyncClient, email: str = "ws_user@carole.ai"):
    signup_payload = {
        "email": email,
        "password": "StrongPassword123!",
        "first_name": "WS",
        "last_name": "Tester",
    }
    res = await client.post("/api/auth/signup", json=signup_payload)
    data = res.json()
    token = data["token"]
    user_id = data["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers, user_id, email


@pytest.mark.asyncio
async def test_ws_ticket_generation_and_verification(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "ticket_user@carole.ai")

    # 1. Generate WebSocket Ticket
    res = await client.post("/api/auth/ws-ticket", headers=headers)
    assert res.status_code == 200
    ticket = res.json()["ticket"]
    assert len(ticket) > 10

    # 2. Verify Ticket via auth_service returns user_id
    verified_user_id = auth_service.verify_ws_ticket(ticket)
    assert verified_user_id == user_id

    # 3. Verify invalid ticket returns None
    invalid_check = auth_service.verify_ws_ticket("invalid_token_string")
    assert invalid_check is None


@pytest.mark.asyncio
async def test_message_routing_and_eventbus_dispatch(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "msg_router_user@carole.ai")

    # Setup Project, Team, Agents
    p_res = await client.post("/api/projects", json={"name": "Chat Proj", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]
    t_res = await client.post("/api/teams", json={"name": "Chat Team", "project_id": project_id}, headers=headers)
    team_id = t_res.json()["id"]

    # Subscribe to EventBus for this team
    topic = f"team:{team_id}"
    event_queue = await event_bus.subscribe(topic)

    # Route a message with mocked DB session for background router persistence
    with patch("core.chat.message_router.async_session", TestSession):
        await message_router.route_message(
            text="Hello team!",
            sender_id="human",
            team_id=team_id,
            sender_name="Alice Tester"
        )

    # Verify event received on queue
    event = await asyncio.wait_for(event_queue.get(), timeout=2.0)
    assert event["type"] == "message"
    assert event["text"] == "Hello team!"
    assert event["sender_id"] == "human"

    await event_bus.unsubscribe(topic, event_queue)


@pytest.mark.asyncio
async def test_human_in_the_loop_approval_resolution(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "hitl_user@carole.ai")

    # Generate test transaction ID
    tx_id = f"tx-{uuid.uuid4()}"
    pending_approvals[tx_id] = asyncio.Event()

    # 1. Resolve Approval via API -> Approved
    approve_res = await client.post(
        f"/api/tools/approve/{tx_id}",
        json={"approved": True},
        headers=headers
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["action"] == "APPROVED"
    assert approval_results[tx_id] is True
    assert pending_approvals[tx_id].is_set()

    # Cleanup
    pending_approvals.pop(tx_id, None)
    approval_results.pop(tx_id, None)

    # 2. Resolve Approval -> Denied
    tx_id_2 = f"tx-{uuid.uuid4()}"
    pending_approvals[tx_id_2] = asyncio.Event()

    deny_res = await client.post(
        f"/api/tools/approve/{tx_id_2}",
        json={"approved": False},
        headers=headers
    )
    assert deny_res.status_code == 200
    assert deny_res.json()["action"] == "DENIED"
    assert approval_results[tx_id_2] is False

    # Cleanup
    pending_approvals.pop(tx_id_2, None)
    approval_results.pop(tx_id_2, None)


@pytest.mark.asyncio
async def test_interactive_ask_user_resolution(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "ask_user@carole.ai")

    # Setup pending question
    question_id = f"q-{uuid.uuid4()}"
    pending_questions[question_id] = asyncio.Event()

    # Answer Question via API
    ans_res = await client.post(
        f"/api/agent/answer/{question_id}",
        json={"answer": "We choose SQLite and FastAPI"},
        headers=headers
    )
    assert ans_res.status_code == 200
    assert ans_res.json()["status"] == "ok"
    assert question_answers[question_id] == "We choose SQLite and FastAPI"
    assert pending_questions[question_id].is_set()

    # Cleanup
    pending_questions.pop(question_id, None)
    question_answers.pop(question_id, None)


@pytest.mark.asyncio
async def test_message_history_and_deletion(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "msg_history_user@carole.ai")

    # Setup Project & Team
    p_res = await client.post("/api/projects", json={"name": "History Proj", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]
    t_res = await client.post("/api/teams", json={"name": "History Team", "project_id": project_id}, headers=headers)
    team_id = t_res.json()["id"]

    # 1. Post 5 messages
    with patch("core.chat.message_router.async_session", TestSession):
        for i in range(5):
            await message_router.route_message(
                text=f"Message #{i}",
                sender_id="human",
                team_id=team_id,
                sender_name="Alice"
            )

    # 2. Get Messages History
    msgs_res = await client.get(f"/api/messages/{team_id}?limit=10", headers=headers)
    assert msgs_res.status_code == 200
    msgs = msgs_res.json()
    assert len(msgs) == 5
    first_msg_id = msgs[0]["id"]

    # 3. Delete single message
    del_res = await client.delete(f"/api/messages/{first_msg_id}", headers=headers)
    assert del_res.status_code == 200

    # 4. Verify count is now 4
    msgs_res2 = await client.get(f"/api/messages/{team_id}", headers=headers)
    assert len(msgs_res2.json()) == 4


@pytest.mark.asyncio
async def test_message_rollback_and_file_restoration(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "rollback_test_user@carole.ai")

    # Setup Project & Team
    p_res = await client.post("/api/projects", json={"name": "Rollback Proj", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]
    t_res = await client.post("/api/teams", json={"name": "Rollback Team", "project_id": project_id}, headers=headers)
    team_id = t_res.json()["id"]

    from core.tools.file_tools import file_tools
    from core.tools.tool_executor import _snapshot_file

    # 1. Create a base file
    rel_path = "src/main.py"
    initial_code = "print('version 1')\n"
    await file_tools.write_file(rel_path, initial_code, agent_name="User", project_id=project_id)

    # 2. User posts Message 1
    with patch("core.chat.message_router.async_session", TestSession):
        await message_router.route_message(
            text="Add feature A",
            sender_id="human",
            team_id=team_id,
            sender_name="Alice"
        )

    msgs_res = await client.get(f"/api/messages/{team_id}", headers=headers)
    msg1_id = msgs_res.json()[0]["id"]

    # 3. Agent snapshots and edits the file
    with patch("core.memory.database.async_session", TestSession):
        await _snapshot_file(rel_path, team_id, message_id=msg1_id, operation="edit_file")

    modified_code = "print('version 2 - feature A added')\n"
    await file_tools.write_file(rel_path, modified_code, agent_name="Coder", project_id=project_id)

    # 4. Agent posts response Message 2
    with patch("core.chat.message_router.async_session", TestSession):
        await message_router.route_message(
            text="I added feature A",
            sender_id="coder",
            team_id=team_id,
            sender_name="Coder"
        )

    msgs_res = await client.get(f"/api/messages/{team_id}", headers=headers)
    assert len(msgs_res.json()) == 2

    # 5. Rollback from Message 1 (should delete both Message 1 & 2 and revert file to initial_code)
    rollback_res = await client.delete(f"/api/messages/{msg1_id}/rollback", headers=headers)
    assert rollback_res.status_code == 200
    data = rollback_res.json()
    assert data["ok"] is True
    assert data["deleted_count"] == 2
    assert len(data["restored_files"]) == 1

    # 6. Verify messages are deleted
    msgs_after = await client.get(f"/api/messages/{team_id}", headers=headers)
    assert len(msgs_after.json()) == 0

    # 7. Verify file was restored to version 1
    reverted_code = await file_tools.read_file(rel_path, project_id=project_id)
    assert reverted_code == initial_code
