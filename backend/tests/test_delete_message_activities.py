"""
# backend/tests/test_delete_message_activities.py

Test suite verifying that deleting a message also cascades to:
1. Intermediate tool trace messages (is_intermediate=True).
2. System action messages and tool action pills.
3. Direct child messages referencing parent_message.
4. Deleting a human message deletes all activities and agent responses for that turn.
"""

import pytest
import uuid
from httpx import AsyncClient
from tests.conftest import TestSession
from core.memory.models import Message, Agent


async def create_user_and_team(client: AsyncClient, email: str = "cascade_test@carole.ai"):
    signup_payload = {
        "email": email,
        "password": "StrongPassword123!",
        "first_name": "Cascade",
        "last_name": "Tester",
    }
    res = await client.post("/api/auth/signup", json=signup_payload)
    data = res.json()
    token = data["token"]
    user_id = data["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    p_res = await client.post("/api/projects", json={"name": "Cascade Project", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]

    t_res = await client.post("/api/teams", json={"name": "Cascade Team", "project_id": project_id}, headers=headers)
    team_id = t_res.json()["id"]

    agent_id = str(uuid.uuid4())
    async with TestSession() as s:
        s.add(Agent(
            id=uuid.UUID(agent_id),
            name="Archer",
            role="developer",
            team_id=uuid.UUID(team_id),
            model="openrouter/free",
            system_prompt="You are Archer"
        ))
        await s.commit()

    return headers, user_id, team_id, agent_id


@pytest.mark.asyncio
async def test_delete_assistant_message_deletes_related_activities(client: AsyncClient):
    headers, user_id, team_id, agent_id = await create_user_and_team(client, "test_asst_cascade@carole.ai")
    team_uuid = uuid.UUID(team_id)

    # 1. Populate a turn:
    # - Human message
    # - Intermediate tool trace 1
    # - System action message
    # - Intermediate tool trace 2
    # - Child subagent message (referencing the upcoming assistant message or turn)
    # - Assistant response message
    async with TestSession() as s:
        m_human = Message(
            team_id=team_uuid,
            sender_id="human",
            sender_name="User",
            text="Please search and summarize",
            is_intermediate=False
        )
        s.add(m_human)
        await s.flush()

        m_tool1 = Message(
            team_id=team_uuid,
            sender_id=agent_id,
            sender_name="Archer",
            text="🛠️ **read_file**\n```json\n{\"path\": \"src/app.py\"}\n```\n📄 **Result:**\n```\nfile content\n```",
            is_intermediate=True
        )
        m_sys_action = Message(
            team_id=team_uuid,
            sender_id="system",
            sender_name="System",
            text="Approval Event: tool_start",
            is_intermediate=True
        )
        m_tool2 = Message(
            team_id=team_uuid,
            sender_id=agent_id,
            sender_name="Archer",
            text="🛠️ **execute_command**\n```json\n{\"command\": \"pytest\"}\n```\n📄 **Result:**\n```\npassed\n```",
            is_intermediate=True
        )
        s.add_all([m_tool1, m_sys_action, m_tool2])
        await s.flush()

        m_asst = Message(
            team_id=team_uuid,
            sender_id=agent_id,
            sender_name="Archer",
            text="Here is the final summary after running tools.",
            is_intermediate=False
        )
        s.add(m_asst)
        await s.flush()

        # Child worker message referencing m_asst
        m_child = Message(
            team_id=team_uuid,
            sender_id=str(uuid.uuid4()),
            sender_name="Worker",
            text="<task-notification>Subagent completed</task-notification>",
            is_intermediate=False,
            attachments=[{"type": "parent_message", "id": str(m_asst.id)}]
        )
        s.add(m_child)
        await s.commit()

        asst_id = str(m_asst.id)
        tool1_id = str(m_tool1.id)
        tool2_id = str(m_tool2.id)
        sys_id = str(m_sys_action.id)
        child_id = str(m_child.id)
        human_id = str(m_human.id)

    # Verify initial count is 6 messages
    res = await client.get(f"/api/messages/{team_id}", headers=headers)
    assert len(res.json()) == 6

    # 2. Delete the assistant response message
    del_res = await client.delete(f"/api/messages/{asst_id}", headers=headers)
    assert del_res.status_code == 200
    data = del_res.json()
    assert data["ok"] is True
    deleted_ids = set(data["deleted_ids"])

    # Must contain the assistant message, both intermediate tool traces, system action, and child
    assert asst_id in deleted_ids
    assert tool1_id in deleted_ids
    assert tool2_id in deleted_ids
    assert sys_id in deleted_ids
    assert child_id in deleted_ids

    # Must NOT delete the user's human prompt
    assert human_id not in deleted_ids

    # Verify messages in DB: only the human message remains
    res_after = await client.get(f"/api/messages/{team_id}", headers=headers)
    remaining = res_after.json()
    assert len(remaining) == 1
    assert remaining[0]["id"] == human_id


@pytest.mark.asyncio
async def test_delete_human_message_deletes_entire_turn(client: AsyncClient):
    headers, user_id, team_id, agent_id = await create_user_and_team(client, "test_human_cascade@carole.ai")
    team_uuid = uuid.UUID(team_id)

    # 1. Populate two turns:
    # Turn 1:
    # - Human 1 ("First prompt")
    # - Tool 1
    # - Assistant 1
    # Turn 2:
    # - Human 2 ("Second prompt")
    # - Tool 2
    # - Assistant 2
    async with TestSession() as s:
        h1 = Message(team_id=team_uuid, sender_id="human", text="Turn 1 Prompt", is_intermediate=False)
        s.add(h1)
        await s.flush()

        t1 = Message(team_id=team_uuid, sender_id=agent_id, text="🛠️ **list_dir**", is_intermediate=True)
        s.add(t1)
        await s.flush()

        a1 = Message(team_id=team_uuid, sender_id=agent_id, text="Turn 1 Response", is_intermediate=False)
        s.add(a1)
        await s.flush()

        h2 = Message(team_id=team_uuid, sender_id="human", text="Turn 2 Prompt", is_intermediate=False)
        s.add(h2)
        await s.flush()

        t2 = Message(team_id=team_uuid, sender_id=agent_id, text="🛠️ **read_file**", is_intermediate=True)
        s.add(t2)
        await s.flush()

        a2 = Message(team_id=team_uuid, sender_id=agent_id, text="Turn 2 Response", is_intermediate=False)
        s.add(a2)
        await s.commit()

        h1_id = str(h1.id)
        t1_id = str(t1.id)
        a1_id = str(a1.id)
        h2_id = str(h2.id)
        t2_id = str(t2.id)
        a2_id = str(a2.id)

    # 2. Delete Human 1 message
    del_res = await client.delete(f"/api/messages/{h1_id}", headers=headers)
    assert del_res.status_code == 200
    data = del_res.json()
    deleted_ids = set(data["deleted_ids"])

    # Turn 1 items should be deleted
    assert h1_id in deleted_ids
    assert t1_id in deleted_ids
    assert a1_id in deleted_ids

    # Turn 2 items should NOT be deleted
    assert h2_id not in deleted_ids
    assert t2_id not in deleted_ids
    assert a2_id not in deleted_ids

    # Verify DB state
    res_after = await client.get(f"/api/messages/{team_id}", headers=headers)
    remaining_ids = {m["id"] for m in res_after.json()}
    assert remaining_ids == {h2_id, t2_id, a2_id}
