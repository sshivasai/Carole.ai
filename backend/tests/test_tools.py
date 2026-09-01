import pytest
from core.tools.tool_registry import ToolRegistry
from core.tools.file_tools import file_tools
from core.tools.code_analysis_tools import code_analysis_tools
from core.tools.tool_executor import register_builtin_tools

@pytest.mark.asyncio
async def test_tool_registry_and_permissions():
    register_builtin_tools()
    # 1. Verify registry contains tools
    tools = ToolRegistry.list_all()
    assert len(tools) > 0

    # Verify a few standard tools are registered
    tool_names = [t.name for t in tools]
    assert "create_directory" in tool_names
    assert "count_lines" in tool_names
    assert "copy_file" in tool_names

    # Check permission levels
    create_dir_tool = next(t for t in tools if t.name == "create_directory")
    assert create_dir_tool.permission_default == "safe"

    copy_file_tool = next(t for t in tools if t.name == "copy_file")
    assert copy_file_tool.permission_default == "judge"


@pytest.mark.asyncio
async def test_file_tools_direct(tmp_path):
    # Setup workspace root for testing sandbox
    file_tools.workspace_root = tmp_path

    # 1. Test create_directory
    res = await file_tools.create_directory("test_subdir")
    assert "Success" in res

    # 2. Test copy_file
    src_file = tmp_path / "src.txt"
    src_file.write_text("Hello World", encoding="utf-8")

    res = await file_tools.copy_file("src.txt", "dest.txt")
    assert "Success" in res
    assert (tmp_path / "dest.txt").read_text(encoding="utf-8") == "Hello World"


@pytest.mark.asyncio
async def test_code_analysis_tools_direct(tmp_path):
    # Setup workspace root for testing sandbox
    code_analysis_tools.workspace_root = tmp_path

    # 1. Create a dummy code file
    code_file = tmp_path / "code.py"
    code_file.write_text("def hello():\n    print('hi')\n\n# Todo: test it\n", encoding="utf-8")

    # 2. Count lines
    res = code_analysis_tools.count_lines("code.py")
    assert "4" in res


@pytest.mark.asyncio
async def test_subagent_and_spawn_arg_parsing():
    from core.tools.tool_executor import _wrap_hire_subagent, _wrap_spawn_agent
    from unittest.mock import patch, AsyncMock

    with patch("core.tools.agent_tools.agent_tools.hire_subagent", new_callable=AsyncMock) as mock_hire:
        mock_hire.return_value = "Subagent hired"

        # 1. Positional args (role, task)
        res = await _wrap_hire_subagent(
            {"_positional_args": ["Python Developer", "Create hello.txt"]},
            team_id="team-1"
        )
        assert res == "Subagent hired"
        mock_hire.assert_called_with("Python Developer", "Specialist in Python Developer", "Create hello.txt", "team-1", "", model=None, parent_message_id=None)

        # 2. Raw value string with comma-separated arguments
        res = await _wrap_hire_subagent(
            {"value": '"Python Developer", "Create hello.txt"'},
            team_id="team-1"
        )
        assert res == "Subagent hired"

        # 3. Standard kwargs with role and task
        res = await _wrap_hire_subagent(
            {"role": "Tester", "task": "Run tests"},
            team_id="team-1"
        )
        assert res == "Subagent hired"
        mock_hire.assert_called_with("Tester", "Specialist in Tester", "Run tests", "team-1", "", model=None, parent_message_id=None)

    with patch("core.tools.agent_tools.agent_tools.spawn_agent", new_callable=AsyncMock) as mock_spawn:
        mock_spawn.return_value = "Agent spawned"

        # Positional spawn
        res = await _wrap_spawn_agent(
            {"_positional_args": ["Nova", "Build UI"]},
            team_id="team-1"
        )
        assert res == "Agent spawned"
        mock_spawn.assert_called_with("Nova", "Build UI", "team-1", parent_coordinator_id=None, parent_message_id=None)




@pytest.mark.asyncio
async def test_judge_evaluator_verdict_parsing():
    from core.judge.judge_evaluator import judge_evaluator
    from unittest.mock import patch, AsyncMock

    # 1. Negative reasoning containing "approve" with DENIED verdict must NOT be approved
    negative_llm_response = (
        "<REASONING>I cannot approve this dangerous command execution.</REASONING>\n"
        "<VERDICT>DENIED</VERDICT>"
    )
    with patch("core.llm.multi_model_router.llm_router.generate_completion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = negative_llm_response
        approved, reasoning = await judge_evaluator.evaluate("execute_command", {"command": "rm -rf /"}, "Nova")
        assert approved is False
        assert "cannot approve" in reasoning

    # 2. Positive APPROVED verdict
    positive_llm_response = (
        "<REASONING>Reading this public doc is completely safe.</REASONING>\n"
        "<VERDICT>APPROVED</VERDICT>"
    )
    with patch("core.llm.multi_model_router.llm_router.generate_completion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = positive_llm_response
        approved, reasoning = await judge_evaluator.evaluate("read_file", {"relative_path": "README.md"}, "Nova")
        assert approved is True



