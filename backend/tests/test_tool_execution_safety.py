"""
backend/tests/test_tool_execution_safety.py

Comprehensive tests for the Tool Execution & Sandbox Safety module:
1. Task tools cross-team isolation and team-scoping.
2. File tools workspace containment, traversal prevention, and directory write protection.
3. Shell tools secret redaction (GitHub PAT, OpenAI project keys, Google API keys) and cwd validation.
4. Git tools clone directory containment.
5. Code analysis tools sandbox containment and empty-path prevention.
6. Tool executor wrapper security (execute_command sub_cwd and extract_document path checks).
"""

import os
import uuid
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.memory.models import User, Project, Team, Task
from core.tools.task_tools import task_tools
from core.tools.file_tools import file_tools
from core.tools.shell_tools import shell_tools
from core.tools.git_tools import git_tools
from core.tools.code_analysis_tools import code_analysis_tools
from core.tools.tool_executor import (
    tool_executor,
    _wrap_execute_command,
    _wrap_extract_document,
)


@pytest.mark.asyncio
async def test_task_tools_cross_team_isolation(db_session):
    """Verify that a team cannot update or comment on tasks belonging to another team."""
    # 1. Create test user, project, and two teams
    user = User(email=f"user_{uuid.uuid4().hex[:6]}@test.com", hashed_password="pw", first_name="Test")
    db_session.add(user)
    await db_session.flush()

    project = Project(name="Project Safety", owner_id=user.id)
    db_session.add(project)
    await db_session.flush()

    team_a = Team(name="Team Alpha", project_id=project.id)
    team_b = Team(name="Team Beta", project_id=project.id)
    db_session.add_all([team_a, team_b])
    await db_session.flush()

    # 2. Create Task A under Team A
    task_a = Task(
        title="Sensitive Alpha Task",
        description="Confidential task details",
        status="todo",
        team_id=team_a.id,
    )
    db_session.add(task_a)
    await db_session.commit()

    task_a_id_str = str(task_a.id)
    team_a_id_str = str(team_a.id)
    team_b_id_str = str(team_b.id)

    # 3. Team B attempts to update Task A by full UUID -> must be rejected
    update_res_b = await task_tools.update_task(
        task_id=task_a_id_str,
        status="done",
        team_id=team_b_id_str,
        db=db_session,
    )
    assert update_res_b.startswith("Error: Task")
    assert "not found" in update_res_b.lower()

    # 4. Team B attempts to comment on Task A by full UUID -> must be rejected
    comment_res_b = await task_tools.comment_on_task(
        task_id=task_a_id_str,
        text="Unauthorized comment",
        author_id="intruder",
        author_name="Intruder",
        team_id=team_b_id_str,
        db=db_session,
    )
    assert comment_res_b.startswith("Error: Task")
    assert "not found" in comment_res_b.lower()

    # 5. Team A updates and comments on its own task -> must succeed
    update_res_a = await task_tools.update_task(
        task_id=task_a_id_str,
        status="in_progress",
        team_id=team_a_id_str,
        db=db_session,
    )
    assert "Updated task" in update_res_a or "updated:" in update_res_a.lower()

    comment_res_a = await task_tools.comment_on_task(
        task_id=task_a_id_str,
        text="Legitimate team comment",
        author_id="lead",
        author_name="Team Lead",
        team_id=team_a_id_str,
        db=db_session,
    )
    assert "Task updated" in comment_res_a or "updated:" in comment_res_a.lower() or "Legitimate" in comment_res_a or not comment_res_a.startswith("Error")


@pytest.mark.asyncio
async def test_file_tools_sandbox_and_directory_protection(tmp_path):
    """Verify file_tools path traversal blocking and directory overwrite protection."""
    # Test path traversal prevention
    with pytest.raises((ValueError, PermissionError)):
        await file_tools._resolve_safe_path("../../../outside.txt")

    with pytest.raises((ValueError, PermissionError)):
        await file_tools._resolve_safe_path("..\\..\\windows_traversal.txt")

    # Test empty or whitespace path
    with pytest.raises(ValueError, match="Path cannot be empty"):
        await file_tools._resolve_safe_path("")

    with pytest.raises(ValueError, match="Path cannot be empty"):
        await file_tools._resolve_safe_path("   ")

    # Test write_file to an existing directory path
    root = await file_tools.get_workspace_root()
    test_dir = root / "safety_test_folder"
    test_dir.mkdir(parents=True, exist_ok=True)

    rel_dir_path = "safety_test_folder"
    write_res = await file_tools.write_file(
        relative_path=rel_dir_path,
        content="Trying to overwrite folder with file content",
        agent_name="TestAgent",
    )
    assert write_res.message.startswith("Error:")
    assert "directory" in write_res.message.lower()

    # Clean up test directory
    test_dir.rmdir()


@pytest.mark.asyncio
async def test_file_tools_diff_files_safety():
    """Verify diff_files resolves safe paths and handles non-existent or outside files safely."""
    # Valid file diff
    await file_tools.write_file("diff_test_a.txt", "line1\nline2\n", agent_name="Test")
    await file_tools.write_file("diff_test_b.txt", "line1\nmodified line2\n", agent_name="Test")

    diff = await file_tools.diff_files("diff_test_a.txt", "diff_test_b.txt")
    assert "-line2" in diff
    assert "+modified line2" in diff

    # Diff with path traversal in either path must return error
    diff_err = await file_tools.diff_files("diff_test_a.txt", "../secret.txt")
    assert diff_err.startswith("Error:")
    assert "outside the workspace" in diff_err

    # Cleanup
    await file_tools.delete_file("diff_test_a.txt", agent_name="Test")
    await file_tools.delete_file("diff_test_b.txt", agent_name="Test")


def test_shell_tools_secret_redaction():
    """Verify modern and legacy tokens are redacted from command execution logs."""
    commands_to_test = [
        "git clone https://ghp_123456789012345678901234567890123456@github.com/repo.git",
        "curl -H 'Authorization: Bearer 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'",
        "export OPENAI_API_KEY=sk-proj-1234567890abcdef1234567890",
        "export OPENAI_KEY=sk-1234567890abcdef1234567890abcdef12",
        "echo sk-proj-1234567890abcdef1234567890",
        "gcloud config set api_key AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q",
    ]

    for raw_cmd in commands_to_test:
        sanitized = shell_tools.sanitize_command(raw_cmd)
        assert "***REDACTED***" in sanitized, f"Expected ***REDACTED*** in sanitized output: {sanitized}"
        # Verify original raw token is NOT in sanitized
        for token_prefix in ["ghp_1234567890", "github_pat_11A2B3", "sk-proj-123456", "AIzaSyA1B2"]:
            assert token_prefix not in sanitized


@pytest.mark.asyncio
async def test_shell_tools_invalid_cwd():
    """Verify executing in a non-existent or invalid directory returns an error."""
    result = await shell_tools.execute_command(
        "echo hello",
        team_id="team_123",
        cwd="C:\\non_existent_folder_xyz_123"
    )
    assert result.startswith("✗ Subprocess Launch Error")
    assert "does not exist or is not a directory" in result


@pytest.mark.asyncio
async def test_git_tools_clone_containment():
    """Verify git clone rejects directory arguments escaping the workspace root."""
    # Traversal directory escaping cwd / workspace root
    res = await git_tools.clone("https://github.com/example/repo.git", directory="../../escaped_repo")
    assert res.startswith("Error:")
    assert "escapes workspace sandbox" in res


def test_code_analysis_tools_sandbox():
    """Verify code_analysis_tools _resolve_safe_path prevents traversal and empty paths."""
    # 1. Direct _resolve_safe_path calls (synchronous)
    with pytest.raises((ValueError, PermissionError)):
        code_analysis_tools._resolve_safe_path("../escaped_file.py")

    with pytest.raises(ValueError, match="Path cannot be empty"):
        code_analysis_tools._resolve_safe_path("")

    with pytest.raises(ValueError, match="Path cannot be empty"):
        code_analysis_tools._resolve_safe_path("   ")

    # 2. Public tool methods return friendly error string on traversal
    func_res = code_analysis_tools.find_function("main", "../escaped_folder")
    assert func_res.startswith("Error:")
    assert "Access Denied" in func_res or "outside sandbox" in func_res

    todo_res = code_analysis_tools.find_todos("   ")
    assert todo_res.startswith("Error:")
    assert "Path cannot be empty" in todo_res


@pytest.mark.asyncio
async def test_tool_executor_wrappers_safety():
    """Verify execute_command and extract_document parameter security in ToolExecutor."""
    # 1. execute_command sub_cwd path traversal check
    exec_res = await _wrap_execute_command({
        "command": "echo test",
        "cwd": "../../traversal_attempt",
    }, team_id="dummy_team_id")
    assert "escapes the workspace root" in exec_res

    # 2. extract_document path traversal check
    extract_res = await _wrap_extract_document({
        "path_or_url": "../../secret_document.pdf",
    }, team_id="dummy_team_id")
    assert "Error: Path '../../secret_document.pdf' is outside workspace boundaries." in extract_res
