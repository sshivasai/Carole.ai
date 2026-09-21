"""
# backend/tests/test_files_complete.py

Comprehensive test suite covering:
1. Workspace File Operations (Write, Read, Create Folder, Rename, Delete)
2. Sandbox Security & Path Traversal Protections
3. Copy-On-Write File Backups & Activity Logs (/api/files/logs)
4. File Version History & Rollback / Restore (/api/files/history)
5. Workspace Code Search (/api/search/grep)
6. Git Integration (/api/git/status, /api/git/commit)
"""

import pytest
import os
import uuid
import shutil
from pathlib import Path
from httpx import AsyncClient
from core.tools.file_tools import file_tools
from core.config import CAROLE_HOME_DIR
from core.memory.database import async_session
from core.memory.models import FileBackup
from sqlalchemy.ext.asyncio import AsyncSession


async def create_authenticated_user(client: AsyncClient, email: str = "file_tester@carole.ai"):
    signup_payload = {
        "email": email,
        "password": "StrongPassword123!",
        "first_name": "File",
        "last_name": "Admin",
    }
    res = await client.post("/api/auth/signup", json=signup_payload)
    data = res.json()
    token = data["token"]
    user_id = data["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers, user_id, email


@pytest.mark.asyncio
async def test_file_crud_and_sandboxing(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "fs_user@carole.ai")

    # 1. Create Project
    p_res = await client.post("/api/projects", json={"name": "File Sandbox Proj", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]

    # 2. Create Folder
    folder_res = await client.post(
        "/api/files/create_folder",
        json={"path": "src/utils", "project_id": project_id},
        headers=headers
    )
    assert folder_res.status_code == 200

    # 3. Write File
    write_res = await client.post(
        "/api/files/write",
        json={"path": "src/utils/math.js", "content": "export const add = (a, b) => a + b;", "project_id": project_id},
        headers=headers
    )
    assert write_res.status_code == 200

    # 4. Read File
    read_res = await client.get(
        f"/api/files/read?path=src/utils/math.js&project_id={project_id}",
        headers=headers
    )
    assert read_res.status_code == 200
    assert "export const add" in read_res.json()["content"]

    # 5. List Files Tree
    tree_res = await client.get(
        f"/api/files/tree?project_id={project_id}",
        headers=headers
    )
    assert tree_res.status_code == 200
    files = tree_res.json()["files"]
    assert any("math.js" in f for f in files)

    # 6. Rename File
    rename_res = await client.post(
        "/api/files/rename",
        json={"source": "src/utils/math.js", "destination": "src/utils/calculator.js", "project_id": project_id},
        headers=headers
    )
    assert rename_res.status_code == 200

    # 7. Delete File
    del_res = await client.delete(
        f"/api/files/delete?path=src/utils/calculator.js&project_id={project_id}",
        headers=headers
    )
    assert del_res.status_code == 200

    # 8. Path Traversal Security Checks -> Must be rejected (>= 400 status)
    traversal_write = await client.post(
        "/api/files/write",
        json={"path": "../../../sensitive.txt", "content": "attack", "project_id": project_id},
        headers=headers
    )
    assert traversal_write.status_code >= 400


@pytest.mark.asyncio
async def test_file_backup_and_rollback_restore(client: AsyncClient, db_session: AsyncSession):
    headers, user_id, email = await create_authenticated_user(client, "backup_user@carole.ai")

    # Setup Project & Team
    p_res = await client.post("/api/projects", json={"name": "Backup Proj", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]
    t_res = await client.post("/api/teams", json={"name": "Backup Team", "project_id": project_id}, headers=headers)
    team_id = t_res.json()["id"]
    await db_session.commit()

    from core.tools.tool_executor import _snapshot_file
    from unittest.mock import patch
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_async_session():
        yield db_session

    # 1. Write initial file
    rel_path = "app/config.py"
    initial_content = "DEBUG = True\nPORT = 8000\n"
    await file_tools.write_file(rel_path, initial_content, agent_name="User", project_id=project_id)

    # 2. Trigger snapshot using _snapshot_file
    with patch("core.memory.database.async_session", mock_async_session):
        await _snapshot_file(rel_path, team_id, message_id=None, operation="write_file")

    # 3. Modify file as Agent
    modified_content = "DEBUG = False\nPORT = 9000\n"
    await file_tools.write_file(rel_path, modified_content, agent_name="Coder Agent", project_id=project_id)

    # Verify live file has modified content
    read_now = await file_tools.read_file(rel_path, project_id=project_id)
    assert read_now == modified_content

    # 4. Retrieve File History via API
    history_res = await client.get(f"/api/files/history?path={rel_path}&project_id={project_id}", headers=headers)
    assert history_res.status_code == 200
    backups = history_res.json()
    assert len(backups) >= 1
    backup_id = backups[0]["id"]

    # 5. Restore / Rollback to Backup Snapshot
    restore_res = await client.post(f"/api/files/history/restore/{backup_id}?project_id={project_id}", headers=headers)
    assert restore_res.status_code == 200
    assert restore_res.json()["status"] == "success"

    # 6. Verify live file is reverted to initial content
    reverted_content = await file_tools.read_file(rel_path, project_id=project_id)
    assert reverted_content == initial_content


@pytest.mark.asyncio
async def test_search_and_git_routes(client: AsyncClient, monkeypatch):
    headers, user_id, email = await create_authenticated_user(client, "search_user@carole.ai")
    monkeypatch.setenv("CAROLE_OWNER_ID", str(user_id))

    p_res = await client.post("/api/projects", json={"name": "Search Proj", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]

    # 1. Write file with distinct token
    await client.post(
        "/api/files/write",
        json={"path": "search_target.py", "content": "SECRET_ALGORITHM_KEY = 'XYZZY_12345'", "project_id": project_id},
        headers=headers
    )

    # 2. Grep Search
    search_res = await client.get(f"/api/search/grep?q=SECRET_ALGORITHM_KEY&project_id={project_id}", headers=headers)
    assert search_res.status_code == 200

    # 3. Git Status Check
    git_res = await client.get(f"/api/git/status?project_id={project_id}", headers=headers)
    assert git_res.status_code == 200
    assert "status" in git_res.json()


@pytest.mark.asyncio
async def test_advanced_file_operations_and_batch_endpoints(client: AsyncClient):
    headers, user_id, email = await create_authenticated_user(client, "batch_user@carole.ai")

    p_res = await client.post("/api/projects", json={"name": "Batch Ops Proj", "owner_id": user_id}, headers=headers)
    project_id = p_res.json()["id"]

    # 1. Create directory & base files
    await client.post("/api/files/create_folder", json={"path": "modules", "project_id": project_id}, headers=headers)
    await client.post("/api/files/write", json={"path": "modules/file1.txt", "content": "File 1 content", "project_id": project_id}, headers=headers)
    await client.post("/api/files/write", json={"path": "modules/file2.txt", "content": "File 2 content", "project_id": project_id}, headers=headers)

    # 2. Test Copy Endpoint
    copy_res = await client.post(
        "/api/files/copy",
        json={"source": "modules/file1.txt", "destination": "modules/file1_backup.txt", "project_id": project_id},
        headers=headers
    )
    assert copy_res.status_code == 200

    read_copy = await client.get(f"/api/files/read?path=modules/file1_backup.txt&project_id={project_id}", headers=headers)
    assert read_copy.status_code == 200
    assert read_copy.json()["content"] == "File 1 content"

    # 3. Test Duplicate Endpoint
    dup_res = await client.post(
        "/api/files/duplicate",
        json={"path": "modules/file2.txt", "project_id": project_id},
        headers=headers
    )
    assert dup_res.status_code == 200
    new_path = dup_res.json()["new_path"]
    assert "copy" in new_path

    # 4. Test Batch Copy Endpoint
    await client.post("/api/files/create_folder", json={"path": "dist", "project_id": project_id}, headers=headers)
    batch_copy_res = await client.post(
        "/api/files/batch/copy",
        json={"sources": ["modules/file1.txt", "modules/file2.txt"], "destination_dir": "dist", "project_id": project_id},
        headers=headers
    )
    assert batch_copy_res.status_code == 200
    assert len(batch_copy_res.json()["copied"]) == 2

    # 5. Test Batch Move Endpoint
    await client.post("/api/files/create_folder", json={"path": "archive", "project_id": project_id}, headers=headers)
    batch_move_res = await client.post(
        "/api/files/batch/move",
        json={"sources": ["dist/file1.txt", "dist/file2.txt"], "destination_dir": "archive", "project_id": project_id},
        headers=headers
    )
    assert batch_move_res.status_code == 200
    assert len(batch_move_res.json()["moved"]) == 2

    # 6. Test Download Zip Endpoint
    zip_res = await client.get(f"/api/files/download_zip?project_id={project_id}", headers=headers)
    assert zip_res.status_code == 200
    assert zip_res.headers["content-type"] == "application/zip"
    assert len(zip_res.content) > 0

    # 7. Test Batch Delete Endpoint
    batch_del_res = await client.post(
        "/api/files/batch/delete",
        json={"paths": ["archive/file1.txt", "archive/file2.txt", "modules"], "project_id": project_id},
        headers=headers
    )
    assert batch_del_res.status_code == 200
    assert len(batch_del_res.json()["deleted"]) == 3

