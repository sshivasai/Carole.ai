import pytest
import asyncio
from core.tools.context import CancellationToken, ToolPermissionContext

def test_cancellation_token():
    token = CancellationToken()
    assert not token.is_cancelled
    
    token.cancel()
    assert token.is_cancelled

def test_tool_permission_context():
    # Test always_allow and always_deny
    ctx = ToolPermissionContext(
        always_allow={"file_write", "file_read"},
        always_deny={"shell_exec"}
    )
    
    assert "file_write" in ctx.always_allow
    assert "shell_exec" in ctx.always_deny
    assert "git_commit" not in ctx.always_allow
    assert "git_commit" not in ctx.always_deny
