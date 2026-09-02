import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from core.tools.mcp_client import MCPManager

@pytest.mark.asyncio
async def test_mcp_manager_per_server_exit_stacks():
    mgr = MCPManager()
    assert hasattr(mgr, "exit_stacks")
    assert isinstance(mgr.exit_stacks, dict)

@pytest.mark.asyncio
async def test_mcp_manager_timeout_and_error_message():
    mgr = MCPManager()
    server_name = "mock_timeout_server"
    key = ("None", "global", server_name)

    # Simulate timeout error during connection
    with patch("core.tools.mcp_client.safe_stdio_client", side_effect=asyncio.TimeoutError):
        with pytest.raises(asyncio.TimeoutError):
            await mgr.connect_stdio_server(
                server_name=server_name,
                command="dummy_cmd",
                args=[]
            )

    status_entry = mgr.statuses.get(key)
    assert status_entry is not None
    assert status_entry["status"] == "error"
    assert "timed out" in status_entry["error"].lower()

@pytest.mark.asyncio
async def test_mcp_manager_clean_disconnect():
    mgr = MCPManager()
    server_name = "mock_disconnect_server"
    key = ("None", "global", server_name)

    mgr.statuses[key] = {"server_name": server_name, "status": "connected", "tools": []}
    mock_stack = AsyncMock()
    mgr.exit_stacks[key] = mock_stack

    await mgr.disconnect_server(server_name=server_name)
    assert key not in mgr.statuses
    assert key not in mgr.exit_stacks
    mock_stack.aclose.assert_awaited_once()
