import pytest
from pathlib import Path
from core.tools.file_tools import file_tools, _validate_code_syntax

def test_syntax_validator_valid_python():
    code = """
def add(a: int, b: int) -> int:
    return a + b

class Calculator:
    def __init__(self):
        self.val = 0
"""
    err = _validate_code_syntax("test.py", code)
    assert err is None


def test_syntax_validator_invalid_python_missing_colon():
    bad_code = """
def broken_func(x)
    return x * 2
"""
    err = _validate_code_syntax("broken.py", bad_code)
    assert err is not None
    assert "Syntax Error" in err
    assert "line 2" in err


def test_syntax_validator_invalid_python_indentation():
    bad_code = """
def func():
return 42
"""
    err = _validate_code_syntax("indent.py", bad_code)
    assert err is not None
    assert "Syntax Error" in err


def test_syntax_validator_valid_json():
    valid_json = '{"name": "Archer", "role": "Orchestrator", "items": [1, 2, 3]}'
    err = _validate_code_syntax("config.json", valid_json)
    assert err is None


def test_syntax_validator_invalid_json():
    bad_json = '{"name": "Archer", "role": "Orchestrator",}'  # trailing comma
    err = _validate_code_syntax("config.json", bad_json)
    assert err is not None
    assert "JSON Syntax Error" in err


def test_syntax_validator_js_ts_unmatched_delimiter():
    bad_ts = """
function greet(name: string) {
    if (name) {
        console.log("hello " + name;
    }
}
"""
    err = _validate_code_syntax("greet.ts", bad_ts)
    assert err is not None
    assert "Syntax Error" in err


@pytest.mark.asyncio
async def test_file_tools_write_blocks_invalid_syntax(tmp_path):
    # Set workspace_root to temp dir
    orig_root = file_tools.workspace_root
    file_tools.workspace_root = tmp_path
    try:
        bad_code = "def bad_func(\n    pass"
        res = await file_tools.write_file("bad.py", bad_code)
        assert "Syntax Error" in res.message
        # Verify file was NOT written to disk
        target = tmp_path / "bad.py"
        assert not target.exists()
    finally:
        file_tools.workspace_root = orig_root


@pytest.mark.asyncio
async def test_file_tools_edit_blocks_invalid_syntax(tmp_path):
    orig_root = file_tools.workspace_root
    file_tools.workspace_root = tmp_path
    try:
        good_code = "def foo():\n    return 1\n"
        await file_tools.write_file("mod.py", good_code)
        target = tmp_path / "mod.py"
        assert target.exists()

        # Read first so pre-read passes
        await file_tools.read_file("mod.py")

        # Now attempt edit with syntax error
        res = await file_tools.edit_file(
            relative_path="mod.py",
            target_content="def foo():\n    return 1",
            replacement_content="def foo()\n    return 1"  # missing colon
        )
        assert "Syntax Error" in res.message

        # Verify disk file still has original content
        with open(target, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == good_code
    finally:
        file_tools.workspace_root = orig_root
