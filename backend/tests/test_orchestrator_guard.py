import pytest
from core.tools.tool_executor import tool_executor
from core.tools.context import ToolExecutionContext, CancellationToken
from core.agent.coordinator import CoordinatorAgent, OrchestratorAgent

@pytest.mark.asyncio
async def test_orchestrator_write_tool_blocked_by_permission():
    """Explicit permissions, rather than role titles, deny file modifications."""
    exec_context = ToolExecutionContext(
        agent_id="test-orch-id",
        agent_name="Archer",
        team_id="test-team-id",
        cancellation_token=CancellationToken(),
        agent_role="Orchestrator"
    )

    result = await tool_executor.execute(
        tool_name="write_file",
        arguments={"relative_path": "test.txt", "content": "hello"},
        agent_id="test-orch-id",
        agent_name="Archer",
        team_id="test-team-id",
        permissions={"write_file": "block"},
        context=exec_context
    )

    assert "Execution Blocked" in result


@pytest.mark.asyncio
async def test_orchestrator_mkdir_blocked_by_permission():
    """Explicit permissions can still block directory creation."""
    exec_context = ToolExecutionContext(
        agent_id="test-orch-id",
        agent_name="Archer",
        team_id="test-team-id",
        cancellation_token=CancellationToken(),
        agent_role="Orchestrator"
    )

    result = await tool_executor.execute(
        tool_name="create_directory",
        arguments={"path": "new_dir"},
        agent_id="test-orch-id",
        agent_name="Archer",
        team_id="test-team-id",
        permissions={"create_directory": "block"},
        context=exec_context
    )

    assert "Execution Blocked" in result


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
@pytest.mark.parametrize("path", ["plan.md", "app.py"])
async def test_orchestrator_can_write_when_policy_allows(owned_browser, db_session, path):
    """A role title cannot override an approved tool permission."""
    from unittest.mock import patch, AsyncMock
    import uuid
    from core.memory.models import Agent
    from core.tools.context import ToolPermissionContext
    agent = await db_session.get(Agent, uuid.UUID(owned_browser["agent_id"]))
    agent.role = "Orchestrator"
    await db_session.commit()
    exec_context = ToolExecutionContext(
        agent_id=str(agent.id),
        agent_name="Archer",
        team_id=str(agent.team_id),
        cancellation_token=CancellationToken(),
        agent_role="Orchestrator"
    )

    with patch("core.tools.file_tools.file_tools.write_file", new_callable=AsyncMock) as mock_write:
        mock_write.return_value = "✓ File 'plan.md' written successfully."
        result = await tool_executor.execute(
            tool_name="write_file",
            arguments={"relative_path": path, "content": "# Implementation Plan"},
            agent_id=str(agent.id),
            agent_name="Archer",
            team_id=str(agent.team_id),
            permissions={"write_file": "safe"},
            context=exec_context,
            permission_context=ToolPermissionContext(always_allow={"write_file"}),
        )

        assert "Execution Denied" not in result
        assert "Execution Blocked" not in result
        assert "written successfully" in result

