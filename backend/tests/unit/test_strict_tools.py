import os
import time
import pytest
from pathlib import Path
from core.tools.file_tools import FileTools
from core.tools.shell_tools import ShellTools

@pytest.mark.asyncio
async def test_strict_preread_and_unchanged_stub(tmp_path):
    ft = FileTools(workspace_root=str(tmp_path))
    test_file = "sample.py"
    full_path = tmp_path / test_file
    full_path.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    # 1. edit_file before read_file must fail with pre-read error
    edit_res = await ft.edit_file(test_file, "return 'world'", "return 'carole'", team_id="team_test")
    assert "Error: File 'sample.py' has not been read yet" in edit_res.message
    assert full_path.read_text(encoding="utf-8") == "def hello():\n    return 'world'\n"

    # 2. First read_file call returns full content
    content1 = await ft.read_file(test_file, team_id="team_test")
    assert "def hello():" in content1

    # 3. Second read_file call without changes returns FILE_UNCHANGED_STUB
    content2 = await ft.read_file(test_file, team_id="team_test")
    assert "File unchanged since last read" in content2

    # 4. Read with force=True bypasses stub
    content_forced = await ft.read_file(test_file, team_id="team_test", force=True)
    assert "def hello():" in content_forced

    # 5. edit_file now succeeds after read_file
    edit_res2 = await ft.edit_file(test_file, "return 'world'", "return 'carole'", team_id="team_test")
    assert "Success: Modified" in edit_res2.message
    assert "return 'carole'" in full_path.read_text(encoding="utf-8")

    # 6. If modified externally on disk, edit_file must catch modified-since-read
    time.sleep(0.05)
    # External modification: change mtime
    full_path.write_text("def hello():\n    return 'external'\n", encoding="utf-8")
    os.utime(full_path, (time.time() + 2, time.time() + 2))

    edit_res3 = await ft.edit_file(test_file, "return 'external'", "return 'carole'", team_id="team_test")
    assert "Error: File 'sample.py' has been modified on disk since it was last read" in edit_res3.message

@pytest.mark.asyncio
async def test_shell_tool_exclusivity():
    st = ShellTools()

    # Standalone cat command must be intercepted
    res_cat = await st.execute_command("cat src/main.py", team_id="test_team")
    assert "Strict Tool Policy Violation: Do NOT use shell commands like 'cat/head/tail/Get-Content'" in res_cat

    # Standalone Get-Content must be intercepted
    res_gc = await st.execute_command("Get-Content src/main.py", team_id="test_team")
    assert "Strict Tool Policy Violation" in res_gc

    # sed -i must be intercepted
    res_sed = await st.execute_command("sed -i 's/foo/bar/' file.py", team_id="test_team")
    assert "Strict Tool Policy Violation: Do NOT use 'sed -i' or 'awk'" in res_sed

    # cat << EOF must be intercepted
    res_heredoc = await st.execute_command("cat << 'EOF' > file.py\ncode\nEOF", team_id="test_team")
    assert "Strict Tool Policy Violation: Do NOT use shell heredocs" in res_heredoc

    # Legitimate command passes policy check
    res_py = await st.execute_command("python --version", team_id="test_team")
    assert "Python" in res_py or "exit code" not in res_py or "Subprocess Execution" in res_py
