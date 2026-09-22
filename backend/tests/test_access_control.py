import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from core.tools.tool_registry import ToolRegistry
from core.tools.tool_executor import (
    ToolExecutor, register_builtin_tools,
    _resolve_gate_level, _matches_skip_judge, _get_effective_permissions, _apply_judge_disabled_fallback
)
from core.tools.context import ToolPermissionContext


@pytest.fixture(autouse=True)
def setup_tools():
    register_builtin_tools()


@pytest.mark.asyncio
async def test_resolve_gate_levels():
    # 1. Defaults
    config = {
        "enable_judge": True,
        "judge_fallback": "always_ask",
        "categories": {
            "view": "allow",
            "edit": "judge",
            "create": "judge",
            "delete": "always_ask",
            "execute": "judge",
            "git": "allow",
            "web": "allow",
            "browser": "allow",
            "subagents": "allow",
            "scheduler": "judge",
        },
        "overrides": {
            "git_push": "always_ask",
            "execute_command": "block",
        },
        "custom_skip_judge": {"file_patterns": [], "command_prefixes": []},
    }

    assert _resolve_gate_level("read_file", config) == "safe"
    assert _resolve_gate_level("edit_file", config) == "judge"
    assert _resolve_gate_level("delete_file", config) == "human"
    # Overrides take precedence
    assert _resolve_gate_level("git_push", config) == "human"
    assert _resolve_gate_level("execute_command", config) == "block"


@pytest.mark.asyncio
async def test_matches_skip_judge_whitelist():
    config = {
        "custom_skip_judge": {
            "file_patterns": ["*.md", "docs/**", ".carole/**"],
            "command_prefixes": ["git status", "npm test", "pytest"],
        }
    }

    # File pattern matching
    assert _matches_skip_judge("write_file", {"relative_path": "README.md"}, config) is True
    assert _matches_skip_judge("edit_file", {"relative_path": "docs/architecture.txt"}, config) is True
    assert _matches_skip_judge("write_file", {"relative_path": "src/main.py"}, config) is False

    # Command prefix matching
    assert _matches_skip_judge("execute_command", {"command": "git status"}, config) is True
    assert _matches_skip_judge("execute_command", {"command": "npm test -- --watch"}, config) is True
    assert _matches_skip_judge("execute_command", {"command": "rm -rf /"}, config) is False


@pytest.mark.asyncio
async def test_block_permission_level():
    executor = ToolExecutor()
    config = {
        "enable_judge": True,
        "judge_fallback": "always_ask",
        "categories": {
            "execute": "block",
        },
        "overrides": {},
        "custom_skip_judge": {"file_patterns": [], "command_prefixes": []},
    }

    result = await executor.execute(
        tool_name="execute_command",
        arguments={"command": "ls"},
        agent_id="agent-1",
        agent_name="TestAgent",
        team_id="team-1",
        permissions=config,
    )
    assert "Execution Blocked" in result
    assert "execute_command" in result


@pytest.mark.asyncio
async def test_judge_disabled_fallback_allow(owned_browser, db_session, monkeypatch):
    import uuid
    from core.memory.models import Agent
    agent = await db_session.get(Agent, uuid.UUID(owned_browser["agent_id"]))
    executor = ToolExecutor()
    config = {
        "enable_judge": False,
        "judge_fallback": "allow",
        "categories": {
            "edit": "judge",
        },
        "overrides": {},
        "custom_skip_judge": {"file_patterns": [], "command_prefixes": []},
    }

    # Disabling the judge requires global policy too; an agent cannot weaken it.
    monkeypatch.setattr("core.llm.config_manager.load_config", lambda: {"access_control": config})

    # Mock _run_tool to verify it executes without judge or human gating
    with patch.object(executor, "_run_tool", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "Success: edited"
        res = await executor.execute(
            tool_name="edit_file",
            arguments={"relative_path": "src/app.py", "target_content": "a", "replacement_content": "b"},
            agent_id=str(agent.id),
            agent_name="TestAgent",
            team_id=str(agent.team_id),
            permissions=config,
        )
        assert res == "Success: edited"
        assert mock_run.called


@pytest.mark.asyncio
async def test_permission_context_always_deny():
    executor = ToolExecutor()
    config = {
        "enable_judge": False,
        "judge_fallback": "allow",
        "categories": {"view": "allow"},
        "overrides": {},
        "custom_skip_judge": {"file_patterns": [], "command_prefixes": []},
    }

    perm_ctx = ToolPermissionContext(
        always_allow=set(),
        always_deny={"read_file"}
    )

    result = await executor.execute(
        tool_name="read_file",
        arguments={"relative_path": "test.txt"},
        agent_id="agent-1",
        agent_name="TestAgent",
        team_id="team-1",
        permissions=config,
        permission_context=perm_ctx,
    )
    assert "Execution Cancelled" in result
    assert "read_file" in result
