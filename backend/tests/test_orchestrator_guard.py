import pytest
from core.tools.tool_executor import tool_executor
from core.tools.context import ToolExecutionContext, CancellationToken
from core.agent.coordinator import CoordinatorAgent, OrchestratorAgent

@pytest.mark.asyncio
async def test_orchestrator_write_tool_blocked():
    """Verify that an Orchestrator is hard-blocked from file modifications."""
    exec_context = ToolExecutionContext(
        agent_id="test-orch-id",
        agent_name="Archer",
        team_id="test-team-id",
        cancellation_token=CancellationToken(),
        agent_role="Orchestrator"
    )

    result = await tool_executor.execute(
        tool_name="write_file",
        arguments={"path": "test.txt", "content": "hello"},
        agent_id="test-orch-id",
        agent_name="Archer",
        team_id="test-team-id",
        permissions={},
        context=exec_context
    )

    assert "Execution Denied" in result
    assert "As an Orchestrator, you must NOT write or modify project files directly" in result
    assert "spawn_agent" in result


@pytest.mark.asyncio
async def test_orchestrator_mkdir_blocked():
    """Verify that an Orchestrator is blocked from create_directory."""
    exec_context = ToolExecutionContext(
        agent_id="test-orch-id",
        agent_name="Archer",
        team_id="test-team-id",
        cancellation_token=CancellationToken(),
        agent_role="Orchestrator"
    )

    result = await tool_executor.execute(
        tool_name="create_directory",
        arguments={"directory_path": "new_dir"},
        agent_id="test-orch-id",
        agent_name="Archer",
        team_id="test-team-id",
        permissions={},
        context=exec_context
    )

    assert "Execution Denied" in result
    assert "Orchestrator" in result


@pytest.mark.asyncio
async def test_coder_not_blocked_by_orchestrator_rule():
    """Verify that a Coder (e.g. Nova) is NOT blocked by the orchestrator rule."""
    exec_context = ToolExecutionContext(
        agent_id="test-coder-id",
        agent_name="Nova",
        team_id="test-team-id",
        cancellation_token=CancellationToken(),
        agent_role="Coder"
    )

    # Calling with empty path should fail argument validation, NOT the orchestrator rule
    result = await tool_executor.execute(
        tool_name="write_file",
        arguments={},
        agent_id="test-coder-id",
        agent_name="Nova",
        team_id="test-team-id",
        permissions={"write_file": "safe"},
        context=exec_context
    )

    # Should hit parameter validation, not orchestrator denial
    assert "Missing required parameter" in result
    assert "As an Orchestrator" not in result


def test_orchestrator_agent_alias():
    """Verify OrchestratorAgent is alias of CoordinatorAgent."""
    assert OrchestratorAgent is CoordinatorAgent


@pytest.mark.asyncio
async def test_orchestrator_can_write_markdown_files():
    """Verify that an Orchestrator IS allowed to author markdown planning files."""
    from unittest.mock import patch, AsyncMock
    exec_context = ToolExecutionContext(
        agent_id="test-orch-id",
        agent_name="Archer",
        team_id="test-team-id",
        cancellation_token=CancellationToken(),
        agent_role="Orchestrator"
    )

    with patch("core.tools.file_tools.file_tools.write_file", new_callable=AsyncMock) as mock_write:
        mock_write.return_value = "✓ File 'plan.md' written successfully."
        result = await tool_executor.execute(
            tool_name="write_file",
            arguments={"relative_path": "plan.md", "content": "# Implementation Plan"},
            agent_id="test-orch-id",
            agent_name="Archer",
            team_id="test-team-id",
            permissions={"write_file": "block"},  # even with block permission, doc write fast-paths
            context=exec_context
        )

        assert "Execution Denied" not in result
        assert "Execution Blocked" not in result
        assert "written successfully" in result

