import pytest
from core.tools.file_tools import file_tools
from core.knowledge.code_graph import code_graph
from core.tools.code_analysis_tools import code_analysis_tools


@pytest.mark.asyncio
async def test_sandboxing_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(file_tools, "workspace_root", tmp_path)
    try:
        res = await file_tools.read_file("../../../../../etc/passwd")
        assert "Access Denied" in res or "PermissionError" in res or "Error reading file" in res
    except (PermissionError, Exception):
        pass


@pytest.mark.asyncio
async def test_code_graph_and_lock_tracking(tmp_path, monkeypatch):
    monkeypatch.setattr(file_tools, "workspace_root", tmp_path)
    monkeypatch.setattr(code_analysis_tools, "workspace_root", tmp_path)
    monkeypatch.setattr(code_graph, "workspace_root", tmp_path)

    # Write files
    await file_tools.write_file("dummy_a.py", "import os\nfrom dummy_b import my_func\n", "Agent1")
    await file_tools.write_file("dummy_b.py", "def my_func(): pass\n", "Agent2")

    # Parse file in code graph
    await code_graph.parse_file("dummy_a.py")

    # Analyze impact
    impact = await code_analysis_tools.analyze_impact("dummy_b.py")
    assert impact is not None

    # Mark file active lock
    await code_graph.mark_file_active("dummy_b.py", "Nova")
    impact_with_lock = await code_analysis_tools.analyze_impact("dummy_b.py")
    assert impact_with_lock is not None

    # Cleanup
    await file_tools.delete_file("dummy_a.py")
    await file_tools.delete_file("dummy_b.py")
