"""
backend/tests/test_external_path_and_workspace.py

Comprehensive tests for:
1. Reading external files and directories on disk via read_file, list_directory, grep_search, and glob_search.
2. Copying external files and entire directory trees into the project workspace via copy_file.
3. Editing copied files inside the workspace (strict pre-read + backup snapshots).
4. Enforcing sandboxed mutations (blocking write/delete on external paths unless explicitly bound).
5. Binding projects to external directories via custom_workspace_path (get_workspace_root resolution).
6. Executing commands with absolute external cwd in execute_command.
7. CRUD API handling of custom_workspace_path.
"""

import os
import uuid
import pytest
from pathlib import Path

from core.memory.models import User, Project, Team, FileBackup
from core.tools.file_tools import file_tools
from core.tools.tool_executor import _wrap_execute_command, _wrap_copy_file
from core.tools.code_analysis_tools import code_analysis_tools


@pytest.mark.asyncio
async def test_read_external_path_on_the_fly(tmp_path):
    """Verify that read_file and list_directory can inspect existing paths outside the workspace."""
    ext_dir = tmp_path / "external_car_rental"
    ext_dir.mkdir(parents=True, exist_ok=True)

    sample_file = ext_dir / "models.py"
    sample_file.write_text("class RentalCar:\n    pass\n", encoding="utf-8")

    # 1. read_file with absolute path outside Carole workspace
    content = await file_tools.read_file(str(sample_file))
    assert "class RentalCar:" in content

    # 2. list_directory with absolute path outside Carole workspace
    listing = await file_tools.list_directory(str(ext_dir))
    assert "[FILE] models.py" in listing

    # 3. Relative path traversal must still be strictly blocked
    with pytest.raises((ValueError, PermissionError)):
        await file_tools._resolve_safe_path("../../../etc/passwd", allow_out_of_bounds=False)


@pytest.mark.asyncio
async def test_search_external_path(tmp_path):
    """Verify grep_search and glob_search can scan an external directory tree."""
    ext_dir = tmp_path / "external_search_project"
    ext_dir.mkdir(parents=True, exist_ok=True)
    sub = ext_dir / "src"
    sub.mkdir(parents=True, exist_ok=True)

    f1 = sub / "service.py"
    f1.write_text("def book_car(car_id):\n    return True\n", encoding="utf-8")

    # Grep in external path
    grep_res = await file_tools.grep_search("def book_car", str(ext_dir))
    assert "Found 1 match" in grep_res
    assert "service.py:1: def book_car" in grep_res

    # Glob in external path
    glob_res = await file_tools.glob_search("*.py", str(sub))
    assert "service.py" in glob_res


@pytest.mark.asyncio
async def test_code_analysis_external_path(tmp_path):
    """Verify code_analysis_tools can inspect external files."""
    ext_file = tmp_path / "external_analysis.py"
    ext_file.write_text("def calculate_fare():\n    # TODO: add surge pricing\n    return 50\n", encoding="utf-8")

    # find_function on external file
    fn_res = code_analysis_tools.find_function("calculate_fare", str(ext_file))
    assert "calculate_fare" in fn_res

    # find_todos on external file
    todo_res = code_analysis_tools.find_todos(str(ext_file))
    assert "surge pricing" in todo_res


@pytest.mark.asyncio
async def test_copy_file_and_directory_into_workspace(tmp_path):
    """Verify copy_file can import both files and directories from external locations."""
    ext_dir = tmp_path / "external_assets"
    ext_dir.mkdir(parents=True, exist_ok=True)

    ext_file = ext_dir / "config.json"
    ext_file.write_text('{"currency": "USD"}', encoding="utf-8")

    sub_dir = ext_dir / "templates"
    sub_dir.mkdir(parents=True, exist_ok=True)
    (sub_dir / "invoice.html").write_text("<h1>Invoice</h1>", encoding="utf-8")

    # 1. Copy single external file into workspace
    copy_res = await file_tools.copy_file(str(ext_file), "imported_config.json")
    assert copy_res.startswith("Success:")

    read_res = await file_tools.read_file("imported_config.json")
    assert '{"currency": "USD"}' in read_res

    # 2. Copy entire external directory into workspace
    dir_copy_res = await file_tools.copy_file(str(sub_dir), "imported_templates")
    assert dir_copy_res.startswith("Success:")
    assert "Copied directory" in dir_copy_res

    read_tpl = await file_tools.read_file("imported_templates/invoice.html")
    assert "<h1>Invoice</h1>" in read_tpl

    # Clean up workspace artifacts
    await file_tools.delete_file("imported_config.json")
    await file_tools.delete_file("imported_templates/invoice.html")
    # remove the directory
    root = await file_tools.get_workspace_root()
    import shutil
    shutil.rmtree(str(root / "imported_templates"), ignore_errors=True)


@pytest.mark.asyncio
async def test_mutating_external_path_directly_blocked(tmp_path):
    """Verify write_file and delete_file on external paths without project binding are denied."""
    ext_file = tmp_path / "unbound_external.py"
    ext_file.write_text("original", encoding="utf-8")

    # write_file directly to external path must be blocked by sandbox
    res = await file_tools.write_file(str(ext_file), "malicious overwrite", agent_name="Test")
    assert res.message.startswith("Error writing file:")
    assert "Access Denied" in res.message or "outside sandbox" in res.message

    # delete_file directly to external path must be blocked by sandbox
    del_res = await file_tools.delete_file(str(ext_file), agent_name="Test")
    assert del_res.startswith("Error deleting file:")
    assert "Access Denied" in del_res or "outside sandbox" in del_res


@pytest.mark.asyncio
async def test_custom_workspace_path_binding(db_session, tmp_path):
    """Verify that setting custom_workspace_path binds the project workspace to an external directory."""
    user = User(email=f"ws_{uuid.uuid4().hex[:6]}@test.com", hashed_password="pw", first_name="Test")
    db_session.add(user)
    await db_session.flush()

    ext_project_dir = tmp_path / "my_custom_car_rental"
    ext_project_dir.mkdir(parents=True, exist_ok=True)

    project = Project(
        name="Car Rental Bound",
        owner_id=user.id,
        custom_workspace_path=str(ext_project_dir),
    )
    db_session.add(project)
    await db_session.commit()

    project_id = str(project.id)
    file_tools._project_workspace_cache.clear()

    # 1. get_workspace_root returns custom_workspace_path
    resolved_root = await file_tools.get_workspace_root(project_id, db=db_session)
    assert resolved_root == ext_project_dir.resolve()

    # 2. Writing a file scoped to this project writes directly inside custom_workspace_path
    w_res = await file_tools.write_file("app.py", "print('car rental')", agent_name="Dev", project_id=project_id)
    assert w_res.action == "create"
    assert (ext_project_dir / "app.py").exists()
    assert (ext_project_dir / "app.py").read_text(encoding="utf-8") == "print('car rental')"

    # 3. Reading and editing inside custom_workspace_path
    r_res = await file_tools.read_file("app.py", project_id=project_id)
    assert "print('car rental')" in r_res

    e_res = await file_tools.edit_file(
        "app.py",
        target_content="print('car rental')",
        replacement_content="print('car rental v2')",
        agent_name="Dev",
        project_id=project_id,
    )
    assert "Success: Modified" in e_res.message or "Successfully" in e_res.message
    assert (ext_project_dir / "app.py").read_text(encoding="utf-8") == "print('car rental v2')"


@pytest.mark.asyncio
async def test_execute_command_with_external_cwd(tmp_path):
    """Verify execute_command accepts existing absolute directories as cwd."""
    test_cwd = tmp_path / "command_exec_dir"
    test_cwd.mkdir(parents=True, exist_ok=True)

    # Valid absolute cwd
    cmd_res = await _wrap_execute_command({
        "command": "python -c \"import os; print(os.getcwd())\"",
        "cwd": str(test_cwd),
    }, team_id="dummy_team")
    assert str(test_cwd.resolve()).lower() in cmd_res.lower()

    # Non-existent absolute cwd
    bad_cwd = tmp_path / "does_not_exist_folder_abc"
    bad_res = await _wrap_execute_command({
        "command": "python -c \"print('hi')\"",
        "cwd": str(bad_cwd),
    }, team_id="dummy_team")
    assert "Specified cwd directory" in bad_res
    assert "does not exist" in bad_res


@pytest.mark.asyncio
async def test_project_crud_custom_workspace_path(client, db_session, tmp_path):
    """Verify REST API CRUD endpoints persist and return custom_workspace_path."""
    from main import app
    from core.auth.auth_middleware import require_auth

    user = User(email=f"crud_{uuid.uuid4().hex[:6]}@test.com", hashed_password="pw", first_name="CRUD")
    db_session.add(user)
    await db_session.commit()

    user_id_str = str(user.id)
    app.dependency_overrides[require_auth] = lambda: {"sub": user_id_str, "role": "admin"}

    try:
        ext_folder = tmp_path / "api_custom_workspace"
        ext_folder.mkdir(parents=True, exist_ok=True)

        # 1. Create project with custom_workspace_path
        create_resp = await client.post("/api/projects", json={
            "name": "API Project",
            "owner_id": user_id_str,
            "custom_workspace_path": str(ext_folder),
        })
        assert create_resp.status_code == 200, create_resp.text
        data = create_resp.json()
        project_id = data["id"]
        assert data["custom_workspace_path"] == str(ext_folder.resolve())

        # 2. Get single project
        get_resp = await client.get(f"/api/projects/single/{project_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["custom_workspace_path"] == str(ext_folder.resolve())

        # 3. List projects includes custom_workspace_path
        list_resp = await client.get("/api/projects")
        assert list_resp.status_code == 200
        projects = list_resp.json()
        matched = [p for p in projects if p["id"] == project_id]
        assert len(matched) == 1
        assert matched[0]["custom_workspace_path"] == str(ext_folder.resolve())

        # 4. Update project custom_workspace_path
        new_folder = tmp_path / "api_custom_workspace_v2"
        new_folder.mkdir(parents=True, exist_ok=True)
        update_resp = await client.put(f"/api/projects/{project_id}", json={
            "custom_workspace_path": str(new_folder),
        })
        assert update_resp.status_code == 200
        assert update_resp.json()["custom_workspace_path"] == str(new_folder.resolve())

    finally:
        app.dependency_overrides.pop(require_auth, None)
