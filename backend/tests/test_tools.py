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
    res = file_tools.create_directory("test_subdir")
    assert "Success" in res

    # 2. Test copy_file
    src_file = tmp_path / "src.txt"
    src_file.write_text("Hello World", encoding="utf-8")

    res = file_tools.copy_file("src.txt", "dest.txt")
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

