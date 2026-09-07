"""
# backend/tests/test_chat_routing_safety.py

Unit and integration tests verifying safety, concurrency, authorization,
and DoS protection across the Chat, WebSocket, and Message Routing subsystem:

1. WebSocket gateway sender spoofing protection (forces sender_id='human', sanitizes sender_name)
2. Concurrent enqueue race-condition deduplication inside per-agent lock
3. Queue capacity bounding and graceful QueueFull handling
4. Agent snapshot project_id propagation (eliminates redundant DB queries)
5. Cross-team sender agent verification (drops messages if sender agent != target team)
6. Agent cancellation and queue draining atomicity
7. EventBus input validation (empty/invalid topics and malformed messages)
"""

import pytest
import asyncio
import uuid
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient

from tests.conftest import TestSession
from core.chat.event_bus import event_bus, EventBus
from core.chat.message_router import message_router, _AgentSnapshot
from core.memory.models import Agent, Team, Project, Message, User
from core.auth.auth_service import auth_service
from core.config import MAX_QUEUE_SIZE
from sqlalchemy import select


async def create_test_context(client: AsyncClient, email: str = "chat_safety_user@carole.ai"):
    signup_payload = {
        "email": email,
        "password": "StrongPassword123!",
        "first_name": "Chat",
        "last_name": "Tester",
    }
    res = await client.post("/api/auth/signup", json=signup_payload)
    data = res.json()
    token = data["token"]
    user_id = data["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Setup Project & Team
    p_res = await client.post("/api/projects", json={"name": "Chat Safe Proj", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]
    t_res = await client.post("/api/teams", json={"name": "Chat Safe Team", "project_id": project_id}, headers=headers)
    team_id = t_res.json()["id"]

    return headers, user_id, project_id, team_id


@pytest.mark.asyncio
async def test_websocket_sender_spoofing_prevention(client: AsyncClient):
    """Verify that WebSocket clients cannot spoof sender_id='system' or agent UUIDs."""
    headers, user_id, project_id, team_id = await create_test_context(client, "spoof_ws@carole.ai")

    # Generate ticket
    t_res = await client.post("/api/auth/ws-ticket", headers=headers)
    ticket = t_res.json()["ticket"]

    # Mock message_router.route_message to capture routed parameters
    routed_messages = []

    async def _mock_route(text, sender_id, team_id, sender_name=None, attachments=None):
        routed_messages.append({
            "text": text,
            "sender_id": sender_id,
            "team_id": team_id,
            "sender_name": sender_name,
            "attachments": attachments,
        })

    with patch.object(message_router, "route_message", side_effect=_mock_route):
        # We simulate the websocket endpoint logic directly to test the receive loop
        from main import app
        # Create a mock websocket object
        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=[
            # Attempt 1: Spoofing system sender_id
            '{"text": "Malicious system msg", "sender_id": "system", "sender_name": "system"}',
            # Attempt 2: Spoofing agent UUID
            '{"text": "Malicious agent msg", "sender_id": "11111111-1111-1111-1111-111111111111", "sender_name": "Alice"}',
            asyncio.CancelledError(),
        ])
        mock_ws.send_text = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.accept = AsyncMock()

        # Import endpoint function
        from main import websocket_endpoint

        # Execute endpoint with the ticket and TestSession
        with patch("core.memory.database.async_session", TestSession):
            try:
                await websocket_endpoint(mock_ws, team_id, ticket=ticket)
            except asyncio.CancelledError:
                pass

    # Verify both messages were received, but sender_id was forced to 'human'
    assert len(routed_messages) == 2
    for msg in routed_messages:
        assert msg["sender_id"] == "human", f"Expected 'human' but got {msg['sender_id']}"
    # Verify sender_name 'system' was overridden
    assert routed_messages[0]["sender_name"] != "system"
    assert routed_messages[1]["sender_name"] == "Alice"


@pytest.mark.asyncio
async def test_concurrent_enqueue_deduplication():
    """Verify that concurrent _enqueue_agent calls with identical prompts are deduplicated atomically."""
    agent_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    mock_agent = MagicMock()
    mock_agent.id = uuid.UUID(agent_id)
    mock_agent.team_id = uuid.UUID(team_id)
    mock_agent.name = "WorkerAgent"
    mock_agent.role = "Coder"
    mock_agent.model = "claude-3-5"
    mock_agent.system_prompt = "You are a coder"

    # Reset any existing router state for this test agent
    message_router._queues.pop(agent_id, None)
    message_router._workers.pop(agent_id, None)
    message_router._pending.pop(agent_id, None)

    # Worker that stays alive during the test so done_callback doesn't prematurely pop the queue
    worker_hold_event = asyncio.Event()

    async def _mock_worker(*args, **kwargs):
        await worker_hold_event.wait()

    with patch.object(message_router, "_agent_worker", side_effect=_mock_worker):
        # Concurrently enqueue 10 identical prompts
        prompt = "Refactor database models"
        tasks = [
            message_router._enqueue_agent(mock_agent, prompt, db_session=None)
            for _ in range(10)
        ]
        await asyncio.gather(*tasks)

        # Verify only 1 prompt is sitting in pending and in the queue
        q = message_router._queues[agent_id]
        pending = message_router._pending[agent_id]

        assert q.qsize() == 1
        assert len(pending) == 1
        assert pending[0] == prompt

        worker_hold_event.set()

    # Cleanup
    message_router._queues.pop(agent_id, None)
    message_router._workers.pop(agent_id, None)
    message_router._pending.pop(agent_id, None)


@pytest.mark.asyncio
async def test_queue_capacity_overflow_graceful_drop():
    """Verify that enqueuing into a full agent queue drops gracefully without crashing."""
    agent_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    mock_agent = MagicMock()
    mock_agent.id = uuid.UUID(agent_id)
    mock_agent.team_id = uuid.UUID(team_id)
    mock_agent.name = "OverflowAgent"
    mock_agent.role = "Tester"
    mock_agent.model = "claude-3-5"
    mock_agent.system_prompt = "Test prompt"

    message_router._queues.pop(agent_id, None)
    message_router._pending.pop(agent_id, None)

    # Mock queue with tiny maxsize=2
    small_queue = asyncio.Queue(maxsize=2)
    message_router._queues[agent_id] = small_queue
    message_router._pending[agent_id] = []

    with patch.object(message_router, "_agent_worker", new_callable=AsyncMock):
        # Fill queue to capacity (2 items)
        await message_router._enqueue_agent(mock_agent, "Task 1", None)
        await message_router._enqueue_agent(mock_agent, "Task 2", None)
        assert small_queue.qsize() == 2

        # Enqueue 3rd item - should not throw QueueFull exception
        await message_router._enqueue_agent(mock_agent, "Task 3", None)
        assert small_queue.qsize() == 2
        # Task 3 should not be in pending
        assert "Task 3" not in message_router._pending[agent_id]

    # Cleanup
    message_router._queues.pop(agent_id, None)
    message_router._pending.pop(agent_id, None)


@pytest.mark.asyncio
async def test_snapshot_project_id_propagation():
    """Verify that _AgentSnapshot captures project_id directly, avoiding redundant DB queries."""
    agent_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())
    proj_id = str(uuid.uuid4())

    mock_agent = MagicMock()
    mock_agent.id = uuid.UUID(agent_id)
    mock_agent.team_id = uuid.UUID(team_id)
    mock_agent.name = "SnapAgent"
    mock_agent.role = "Worker"
    mock_agent.model = "gpt-4o"
    mock_agent.system_prompt = "Work"

    snap = _AgentSnapshot(mock_agent, project_id=proj_id)
    assert snap.project_id == proj_id
    assert snap.agent_id == agent_id
    assert snap.team_id == team_id


@pytest.mark.asyncio
async def test_cross_team_sender_agent_rejection(client: AsyncClient):
    """Verify that route_message drops messages if sender agent belongs to a different team."""
    headers, user_id, project_id, team_id_a = await create_test_context(client, "team_a@carole.ai")

    # Create Team B
    t2_res = await client.post("/api/teams", json={"name": "Team B", "project_id": project_id}, headers=headers)
    team_id_b = t2_res.json()["id"]

    # Create Agent in Team B
    agent_b_res = await client.post("/api/agents", json={
        "name": "AgentB",
        "role": "Coder",
        "model": "claude-3-5",
        "team_id": team_id_b
    }, headers=headers)
    agent_b_id = agent_b_res.json()["id"]

    # Attempt to route message to Team A with sender_id = Agent B
    with patch("core.chat.message_router.async_session", TestSession):
        await message_router.route_message(
            text="Hello Team A from Team B agent",
            sender_id=agent_b_id,
            team_id=team_id_a,
            sender_name="AgentB"
        )

    # Verify no messages were persisted in Team A
    msgs_res = await client.get(f"/api/messages/{team_id_a}", headers=headers)
    assert msgs_res.status_code == 200
    assert len(msgs_res.json()) == 0, "Cross-team message should have been dropped"


@pytest.mark.asyncio
async def test_cancel_agent_atomicity():
    """Verify that cancel_agent clears pending and drains queue."""
    agent_id = str(uuid.uuid4())
    q = asyncio.Queue()
    await q.put("item1")
    await q.put("item2")

    message_router._queues[agent_id] = q
    message_router._pending[agent_id] = ["item1", "item2"]

    cancelled = message_router.cancel_agent(agent_id, cancel_all=True)
    assert q.empty()
    assert len(message_router._pending[agent_id]) == 0

    message_router._queues.pop(agent_id, None)
    message_router._pending.pop(agent_id, None)


@pytest.mark.asyncio
async def test_event_bus_validation():
    """Verify that EventBus validates topic strings and message types."""
    bus = EventBus()

    # Empty topic subscribe raises ValueError
    with pytest.raises(ValueError, match="Topic must be a non-empty string"):
        await bus.subscribe("")

    with pytest.raises(ValueError, match="Topic must be a non-empty string"):
        await bus.subscribe("   ")

    # Invalid publish (empty topic or non-dict message) is safely ignored without crash
    await bus.publish("", {"type": "test"})
    await bus.publish("valid_topic", "not_a_dict")  # type: ignore

    # Subscribed queue receives valid messages
    q = await bus.subscribe("valid_topic")
    await bus.publish("valid_topic", {"type": "valid"})
    event = await asyncio.wait_for(q.get(), timeout=1.0)
    assert event["type"] == "valid"

    await bus.unsubscribe("valid_topic", q)
