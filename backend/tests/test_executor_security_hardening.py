import pytest
from pathlib import Path
from unittest.mock import patch

from core.tools.tool_registry import ToolRegistry, ToolSpec
from core.tools.tool_executor import (
    _resolve_gate_level,
    tool_executor,
    _wrap_execute_command,
    _wrap_extract_document,
    register_builtin_tools,
)


def test_resolve_gate_level_non_weakening():
    # Register a dummy tool with 'human' default
    spec = ToolSpec(
        name="test_dangerous_tool",
        description="Dangerous tool",
        category="git",
        parameters={},
        handler=lambda args, team_id: "done",
        permission_default="human",
    )
    ToolRegistry.register(spec, force=True)

    # 1. Category setting is "allow" (safe) -> Must NOT downgrade to safe, must stay human
    gate = _resolve_gate_level("test_dangerous_tool", {"categories": {"git": "allow"}, "overrides": {}})
    assert gate == "human"

    # 2. Overrides specify "safe" -> Must NOT downgrade to safe, must stay human
    gate2 = _resolve_gate_level("test_dangerous_tool", {"categories": {}, "overrides": {"test_dangerous_tool": "safe"}})
    assert gate2 == "human"

    # 3. Overrides specify "block" -> Can escalate to block
    gate3 = _resolve_gate_level("test_dangerous_tool", {"categories": {}, "overrides": {"test_dangerous_tool": "block"}})
    assert gate3 == "block"

    # 4. A 'safe' default tool CAN be escalated
    spec_safe = ToolSpec(
        name="test_safe_tool",
        description="Safe tool",
        category="custom",
        parameters={},
        handler=lambda args, team_id: "done",
        permission_default="safe",
    )
    ToolRegistry.register(spec_safe, force=True)

    gate_escalated = _resolve_gate_level("test_safe_tool", {"categories": {"custom": "require_approval"}, "overrides": {}})
    assert gate_escalated == "judge"

    gate_human = _resolve_gate_level("test_safe_tool", {"categories": {}, "overrides": {"test_safe_tool": "human"}})
    assert gate_human == "human"


@pytest.mark.asyncio
async def test_tool_scope_enforcement():
    # Tool scoped to team-AAA
    spec_scoped = ToolSpec(
        name="test_scoped_team_tool",
        description="Scoped tool",
        category="custom",
        parameters={},
        handler=lambda args, team_id: "success",
        permission_default="safe",
        team_id="team-AAA",
    )
    ToolRegistry.register(spec_scoped, force=True)

    # Calling from different team must be rejected
    res = await tool_executor.execute(
        tool_name="test_scoped_team_tool",
        arguments={},
        agent_id="agent-1",
        agent_name="Agent",
        team_id="team-BBB",
        permissions={},
    )
    assert "Execution Denied: Tool is not available to this team." in res

    # Calling from permitted team succeeds
    res_ok = await tool_executor.execute(
        tool_name="test_scoped_team_tool",
        arguments={},
        agent_id="agent-1",
        agent_name="Agent",
        team_id="team-AAA",
        permissions={},
    )
    assert res_ok == "success"


@pytest.mark.asyncio
async def test_strip_reserved_arguments():
    captured_args = {}

    async def capture_handler(args, team_id):
        nonlocal captured_args
        captured_args = dict(args)
        return "ok"

    spec = ToolSpec(
        name="test_strip_args_tool",
        description="Test strip",
        category="custom",
        parameters={"user_param": {"type": "string"}},
        handler=capture_handler,
        permission_default="safe",
    )
    ToolRegistry.register(spec, force=True)

    await tool_executor.execute(
        tool_name="test_strip_args_tool",
        arguments={
            "user_param": "hello",
            "_human_confirmed": True,
            "_server_approved": True,
            "confirm_destructive": True,
        },
        agent_id="agent-1",
        agent_name="Agent",
        team_id="team-1",
        permissions={},
    )

    assert "user_param" in captured_args
    assert "_human_confirmed" not in captured_args
    assert "_server_approved" not in captured_args
    assert "confirm_destructive" not in captured_args


@pytest.mark.asyncio
async def test_execute_command_fails_closed_without_workspace(tmp_path):
    with patch("core.tools.tool_executor._team_cwd", return_value=None):
        res = await _wrap_execute_command({"command": "ls"}, team_id="nonexistent-team")
        assert "Error: Cannot resolve workspace directory for team." in res


@pytest.mark.asyncio
async def test_execute_command_rejects_path_traversal(tmp_path):
    team_root = tmp_path / "workspace"
    team_root.mkdir()

    with patch("core.tools.tool_executor._team_cwd", return_value=team_root):
        # Attempt to escape workspace
        res = await _wrap_execute_command(
            {"command": "ls", "cwd": "../../outside", "_server_approved": True},
            team_id="team-1",
        )
        assert "escapes the workspace root" in res


@pytest.mark.asyncio
async def test_extract_document_guards(tmp_path):
    team_root = tmp_path / "workspace"
    team_root.mkdir()

    with patch("core.tools.tool_executor._team_cwd", return_value=team_root):
        # 1. SSRF URL rejection
        res_ssrf = await _wrap_extract_document(
            {"path_or_url": "http://169.254.169.254/secret"},
            team_id="team-1",
        )
        assert "Error downloading remote document:" in res_ssrf

        # 2. Local path traversal rejection
        res_traversal = await _wrap_extract_document(
            {"path_or_url": "../../etc/passwd"},
            team_id="team-1",
        )
        assert "outside workspace boundaries" in res_traversal

        # 3. Valid local file in workspace
        doc_file = team_root / "sample.txt"
        doc_file.write_text("Extracted text content from file.")

        res_ok = await _wrap_extract_document(
            {"path_or_url": "sample.txt"},
            team_id="team-1",
        )
        assert "Successfully extracted document (.txt):" in res_ok
        assert "Extracted text content from file." in res_ok
