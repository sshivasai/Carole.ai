"""
# backend/tests/test_subtask_isolation_and_guards.py

Tests for Phase 5: Destructive command guardrails, subtask deliverable notifications, and modified files tracking.
"""

import pytest
from core.tools.tool_executor import _wrap_execute_command
from core.agent.react_agent import ReACTAgent


@pytest.mark.asyncio
async def test_destructive_command_blocked():
    # Attempt rm -rf without confirmation
    res1 = await _wrap_execute_command({"command": "rm -rf /tmp/some_dir"}, team_id="default")
    assert "HIGH-RISK DESTRUCTIVE ACTION INTERCEPTED" in res1

    # Attempt DROP TABLE without confirmation
    res2 = await _wrap_execute_command({"command": "psql -c 'DROP TABLE users CASCADE'"}, team_id="default")
    assert "HIGH-RISK DESTRUCTIVE ACTION INTERCEPTED" in res2

    # Attempt git reset --hard without confirmation
    res3 = await _wrap_execute_command({"command": "git reset --hard HEAD~1"}, team_id="default")
    assert "HIGH-RISK DESTRUCTIVE ACTION INTERCEPTED" in res3


def test_subtask_notification_with_deliverables():
    agent = ReACTAgent(
        agent_id="agent-coder-1",
        team_id="team-1",
        project_id="proj-1",
        name="Coder",
        role="Coder",
        model="gpt-4o",
        system_prompt="You are a coder.",
        task_id="task-42",
        parent_coordinator_id="coord-1",
    )

    # Track simulated modified files
    agent._modified_files.add("src/App.tsx")
    agent._modified_files.add("backend/main.py")

    notification = agent._build_task_notification(
        result_text="Implemented the new authentication component and test suite successfully.",
        status="completed"
    )

    assert "<task-notification>" in notification
    assert "<task_id>task-42</task_id>" in notification
    assert "<agent>Coder</agent>" in notification
    assert "<status>completed</status>" in notification
    assert "<files_modified>" in notification
    assert "<file>src/App.tsx</file>" in notification
    assert "<file>backend/main.py</file>" in notification
    assert "Implemented the new authentication component" in notification
