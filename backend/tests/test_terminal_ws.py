import pytest
import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from core.api.terminal_ws import manager, TerminalSession


@pytest.mark.asyncio
async def test_terminal_input_loop_resize_no_fcntl_error():
    """Verify that on Windows, action: resize does not fail with ModuleNotFoundError for fcntl."""
    mock_ws = AsyncMock()
    # First message: resize, second message: terminate
    mock_ws.receive_text.side_effect = [
        json.dumps({"action": "resize", "cols": 120, "rows": 40}),
        json.dumps({"action": "terminate"}),
    ]

    mock_proc = MagicMock()
    session = TerminalSession("test-sess-1", "win_fallback", mock_proc, ".")
    manager.active_sessions[session.session_id] = session

    # Should run without throwing ModuleNotFoundError (fcntl)
    await manager._run_input_loop(mock_ws, session)
    assert session.session_id not in manager.active_sessions


@pytest.mark.asyncio
async def test_terminal_input_loop_input():
    mock_ws = AsyncMock()
    mock_ws.receive_text.side_effect = [
        json.dumps({"action": "input", "data": "dir\r\n"}),
        json.dumps({"action": "terminate"}),
    ]

    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    session = TerminalSession("test-sess-2", "win_fallback", mock_proc, ".")
    manager.active_sessions[session.session_id] = session

    await manager._run_input_loop(mock_ws, session)
    mock_proc.stdin.write.assert_called_with(b"dir\r\n")


def test_discover_windows_shell():
    from core.api.terminal_ws import discover_windows_shell
    shell = discover_windows_shell()
    assert isinstance(shell, str)
    assert len(shell) > 0
