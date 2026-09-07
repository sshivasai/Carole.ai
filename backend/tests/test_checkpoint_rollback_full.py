"""
backend/tests/test_checkpoint_rollback_full.py

Tests full checkpoint rollback:
1. Message cascade deletion
2. FileBackup restoration & unlinking of newly created files
3. Task rollback (delete tasks created >= pivot_time, reset modified tasks)
4. Memory cascade (delete learnings & entities >= pivot_time)
5. Project memory purge endpoint
"""

import pytest
import uuid
import datetime
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from core.memory.models import Message, Task, Learning, EntityMemory, CompactionEvent, FileBackup, Project, Team, User
from sqlalchemy import select

async def create_auth_user(client: AsyncClient, email: str = "rb_tester@carole.ai"):
    signup = {
        "email": email,
        "password": "Password123!",
        "first_name": "Rollback",
        "last_name": "Tester",
    }
    res = await client.post("/api/auth/signup", json=signup)
    data = res.json()
    token = data["token"]
    user_id = data["user"]["id"]
    return {"Authorization": f"Bearer {token}"}, user_id

@pytest.mark.asyncio
async def test_checkpoint_rollback_flow(client: AsyncClient, db_session: AsyncSession):
    headers, user_id = await create_auth_user(client, "checkpoint_test@carole.ai")

    # Create project & team
    p_res = await client.post("/api/projects", json={"name": "Rollback Proj", "owner_id": user_id}, headers=headers)
    assert p_res.status_code == 200
    project_id = p_res.json()["id"]

    t_res = await client.post("/api/teams", json={"name": "Dev Team", "project_id": project_id}, headers=headers)
    assert t_res.status_code == 200
    team_id = t_res.json()["id"]
    team_uuid = uuid.UUID(team_id)

    now = datetime.datetime.now(datetime.timezone.utc)
    t1 = now - datetime.timedelta(minutes=10)
    t2 = now - datetime.timedelta(minutes=5)

    # Insert message 1 (older) and message 2 (newer) directly into DB
    m1_id = uuid.uuid4()
    m2_id = uuid.uuid4()
    db_session.add(Message(id=m1_id, team_id=team_uuid, sender_id="human", text="Turn 1: initial setup", created_at=t1))
    db_session.add(Message(id=m2_id, team_id=team_uuid, sender_id="human", text="Turn 2: build calculator", created_at=t2))
    await db_session.commit()

    import tempfile, os

    # 1. Create a dummy newly created file and record it in FileBackup
    tmp_fd, created_file_path = tempfile.mkstemp(suffix=".py")
    os.close(tmp_fd)
    with open(created_file_path, "w") as f:
        f.write("# newly created file")
    assert os.path.exists(created_file_path)

    db_session.add(FileBackup(
        team_id=team_uuid,
        file_path=created_file_path,
        backup_file_name=None,
        operation="write",
        created_at=now - datetime.timedelta(minutes=2)
    ))
    await db_session.commit()

    # Create a task after m2
    task_res = await client.post("/api/tasks", json={"team_id": team_id, "title": "Build calc.py"}, headers=headers)
    assert task_res.status_code == 200
    task_id = task_res.json()["id"]

    # Create a learning after m2
    learn_res = await client.post("/api/learnings", json={
        "project_id": project_id,
        "team_id": team_id,
        "task_summary": "Calculator task",
        "lesson_rule": "Test rule"
    }, headers=headers)
    assert learn_res.status_code == 200
    learn_id = learn_res.json()["id"]

    # Now execute rollback from message 2
    rb_res = await client.delete(f"/api/messages/{m2_id}/rollback", headers=headers)
    assert rb_res.status_code == 200
    rb_data = rb_res.json()
    assert rb_data["ok"] is True
    assert rb_data["deleted_count"] >= 1
    assert task_id in rb_data.get("deleted_task_ids", [])

    # Verify newly created file was unlinked by rollback
    assert not os.path.exists(created_file_path)

    # Verify task is gone
    tasks_res = await client.get(f"/api/tasks/{team_id}", headers=headers)
    task_ids = [t["id"] for t in tasks_res.json()]
    assert task_id not in task_ids

    # Verify learning is gone
    learnings_res = await client.get(f"/api/learnings?project_id={project_id}&team_id={team_id}", headers=headers)
    learning_ids = [l["id"] for l in learnings_res.json()]
    assert learn_id not in learning_ids

    # Verify message 2 is gone, message 1 remains
    msgs_res = await client.get(f"/api/messages/{team_id}", headers=headers)
    msg_ids = [m["id"] for m in msgs_res.json()]
    assert str(m2_id) not in msg_ids
    assert str(m1_id) in msg_ids


@pytest.mark.asyncio
async def test_purge_project_memory_endpoint(client: AsyncClient):
    headers, user_id = await create_auth_user(client, "purge_mem_test@carole.ai")

    p_res = await client.post("/api/projects", json={"name": "Purge Memory Proj", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]

    t_res = await client.post("/api/teams", json={"name": "Purge Team", "project_id": project_id}, headers=headers)
    team_id = t_res.json()["id"]

    # Add learning and entity memory
    await client.post("/api/learnings", json={
        "project_id": project_id,
        "team_id": team_id,
        "task_summary": "Test task",
        "lesson_rule": "Test rule to purge"
    }, headers=headers)

    await client.post("/api/memories/entities", json={
        "project_id": project_id,
        "team_id": team_id,
        "key": "test_fact",
        "value": "purge_me"
    }, headers=headers)

    # Call purge endpoint
    purge_res = await client.delete(f"/api/projects/{project_id}/memory", headers=headers)
    assert purge_res.status_code == 200
    assert purge_res.json()["ok"] is True

    # Verify learnings and entity memories are empty
    learnings = (await client.get(f"/api/learnings?project_id={project_id}", headers=headers)).json()
    assert len(learnings) == 0

    entities = (await client.get(f"/api/memories/entities?project_id={project_id}", headers=headers)).json()
    assert len(entities) == 0
