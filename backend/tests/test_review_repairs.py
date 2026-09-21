"""Behavioral regressions for the runtime/security review, using disposable data."""
import asyncio
import re
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from core.tools.tool_registry import ToolRegistry, ToolSpec


@pytest.fixture
def isolated_registry(monkeypatch):
    monkeypatch.setattr(ToolRegistry, "_tools", {})
    monkeypatch.setattr(ToolRegistry, "_plugin_tools", {})
    monkeypatch.setattr(ToolRegistry, "_schema_cache", {})


async def test_instance_authority_defaults_to_first_account_and_is_not_email_based(monkeypatch):
    from core.auth.instance_owner import assert_instance_owner
    monkeypatch.delenv("CAROLE_OWNER_ID", raising=False)
    db = SimpleNamespace(scalar=AsyncMock(return_value="first-owner"))
    await assert_instance_owner({"sub": "first-owner"}, db)
    with pytest.raises(HTTPException) as denied_first_account:
        await assert_instance_owner({"sub": "outsider"}, db)
    assert denied_first_account.value.status_code == 403

    monkeypatch.setenv("CAROLE_OWNER_ID", "owner")
    with pytest.raises(HTTPException) as denied:
        await assert_instance_owner({"sub": "outsider", "email": "owner", "role": "admin"}, db)
    assert denied.value.status_code == 403
    await assert_instance_owner({"sub": "owner"}, db)


async def test_one_worker_for_concurrent_first_messages(monkeypatch):
    from core.chat.message_router import MessageRouter
    router = MessageRouter()
    worker = AsyncMock(side_effect=lambda *args: None)
    started = asyncio.Event()
    async def hold(*args):
        started.set()
        await asyncio.Event().wait()
    worker.side_effect = hold
    monkeypatch.setattr(router, "_agent_worker", worker)
    monkeypatch.setattr("core.chat.message_router.event_bus.publish", AsyncMock())
    agent = SimpleNamespace(id="agent", team_id="team", name="A", role="developer", model="test", system_prompt="test")
    try:
        await asyncio.gather(*(router._enqueue_agent(agent, f"work {n}", None) for n in range(5)))
        await started.wait()
        assert worker.call_count == 1
        assert router._queues["agent"].qsize() == 5
        assert len(router._workers) == 1
    finally:
        await router.shutdown()


async def test_terminal_reattach_never_replays_another_project():
    from core.api.terminal_ws import TerminalSession, TerminalSessionManager
    manager = TerminalSessionManager()
    session = TerminalSession("known-id", "subprocess", MagicMock(), ".", project_id="owner-project")
    session.append_output("PRIVATE SCROLLBACK")
    manager.active_sessions[session.session_id] = session
    socket = AsyncMock()
    await manager.connect(socket, session.session_id, project_id="other-project")
    socket.close.assert_awaited_once_with(code=4003)
    socket.accept.assert_not_called()
    socket.send_text.assert_not_called()


async def test_attachment_rejects_local_secrets_and_other_team_media(tmp_path, monkeypatch):
    from core.chat.attachments import normalize_chat_attachments
    team = tmp_path / "team"
    media = team / "Chat_Media"
    media.mkdir(parents=True)
    secret = tmp_path / "secret.png"
    secret.write_bytes(b"private")
    monkeypatch.setattr("core.chat.attachments.file_tools.get_team_carole_dir", AsyncMock(return_value=team))
    with pytest.raises(ValueError, match="uploaded file"):
        await normalize_chat_attachments([{"type": "image/png", "local_path": str(secret)}], "team", "project")
    upload = media / "photo.png"
    upload.write_bytes(b"image")
    result = await normalize_chat_attachments([{"type": "image/png", "local_path": str(upload)}], "team", "project")
    assert result[0]["url"] == "/api/media/project/team/photo.png"


def test_historical_observation_stays_recoverable(tmp_path, monkeypatch):
    from core.agent.react_agent import ReACTAgent
    from core.agent.observation_cache import read_observation
    monkeypatch.setattr("core.agent.observation_cache.CACHE_DIR", tmp_path)
    agent = object.__new__(ReACTAgent)
    agent.team_id, agent.agent_id = "team", "agent"
    agent._get_compaction_config = lambda: {"max_observation_chars": 3000}
    evidence = "key evidence\n" * 100
    messages = [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call", "content": evidence}]}]
    messages += [{"role": "assistant", "content": "next"}] * 6
    compacted = agent._micro_compact(messages)
    preview = compacted[0]["content"][0]["content"]
    artifact = re.search(r'artifact_id="([^"]+)"', preview)[1]
    assert evidence in read_observation(artifact, "team:agent")
    with pytest.raises(FileNotFoundError):
        read_observation(artifact, "other:agent")
    assert agent._micro_compact(compacted) == compacted


async def test_always_allow_cannot_override_hard_block(isolated_registry):
    from core.tools.tool_executor import tool_executor
    from core.tools.context import ToolPermissionContext
    handler = AsyncMock(return_value="executed")
    ToolRegistry.register(ToolSpec("read_example", "test", "filesystem", {}, "safe", handler))
    result = await tool_executor.execute("read_example", {}, "agent", "A", "team",
        permissions={"overrides": {"read_example": "block"}},
        permission_context=ToolPermissionContext(always_allow={"read_example"}))
    assert "Blocked" in result
    handler.assert_not_called()


def test_plugin_reload_replaces_handlers_and_removes_deleted_exports(tmp_path, isolated_registry):
    plugin = tmp_path / "example.py"
    def source(name, value):
        return f'from core.tools.tool_registry import carole_tool\n@carole_tool(name="{name}", description="test", permission_default="safe")\ndef handler(args, team_id):\n    return "{value}"\n'
    plugin.write_text(source("first", "old"))
    ToolRegistry.load_plugin_directory(str(tmp_path))
    plugin.write_text(source("first", "new"))
    ToolRegistry.load_plugin_directory(str(tmp_path))
    assert ToolRegistry.get("first").handler({}, None) == "new"
    plugin.write_text(source("second", "new"))
    ToolRegistry.load_plugin_directory(str(tmp_path))
    assert ToolRegistry.get("first") is None
    plugin.write_text("raise ValueError('bad update')")
    with pytest.raises(ValueError):
        ToolRegistry.load_plugin_directory(str(tmp_path))
    assert ToolRegistry.get("second") is not None
    plugin.unlink()
    ToolRegistry.load_plugin_directory(str(tmp_path))
    assert ToolRegistry.get("second") is None


def test_nested_tool_schemas_and_cache_are_preserved(isolated_registry):
    parameters = {"payload": {"type": "object", "_required": True,
        "properties": {"items": {"type": "array", "items": {"type": "integer"}}}, "required": ["items"]}}
    ToolRegistry.register(ToolSpec("nested", "test", "mcp", parameters, "judge", AsyncMock()))
    schema = ToolRegistry.to_openai_tools()[0]["function"]["parameters"]
    assert schema["required"] == ["payload"]
    assert schema["properties"]["payload"]["required"] == ["items"]
    schema["properties"]["payload"]["properties"].clear()
    fresh = ToolRegistry.to_openai_tools()[0]["function"]["parameters"]
    assert "items" in fresh["properties"]["payload"]["properties"]
    gemini = ToolRegistry.to_gemini_tools()[0]["functionDeclarations"][0]["parameters"]
    assert gemini["properties"]["payload"]["properties"]["items"]["items"]["type"] == "INTEGER"


async def test_mcp_disconnect_is_scoped(isolated_registry):
    from core.tools.mcp_client import MCPManager
    manager = MCPManager()
    for team in ("one", "two"):
        name = "mcp_" + team
        key = (team, "global", "same-server")
        manager.statuses[key] = {"server_name": "same-server", "tools": [name]}
        manager.exit_stacks[key] = AsyncMock()
        ToolRegistry.register(ToolSpec(name, "test", "mcp", {}, "judge", AsyncMock(), team_id=team))
    await manager.disconnect_server(team_id="one", server_name="same-server")
    assert ToolRegistry.get("mcp_one") is None
    assert ToolRegistry.get("mcp_two") is not None
    assert ("two", "global", "same-server") in manager.statuses


async def test_process_timeout_does_not_block_event_loop():
    from core.tools.process_runner import run_process
    ticks = 0
    async def heartbeat():
        nonlocal ticks
        for _ in range(5):
            await asyncio.sleep(.02)
            ticks += 1
    pulse = asyncio.create_task(heartbeat())
    with pytest.raises(TimeoutError):
        await run_process([sys.executable, "-c", "import time; time.sleep(30)"], timeout=.2)
    await pulse
    assert ticks == 5


async def test_mcp_real_transport_reconnects_without_cross_scope_handlers(tmp_path, isolated_registry, monkeypatch):
    from core.tools.mcp_client import MCPManager
    monkeypatch.setenv("CAROLE_TEST_SECRET", "must-not-be-inherited")
    script = tmp_path / "server.py"
    script.write_text('try:\n    from mcp.server.mcpserver import MCPServer as FastMCP\nexcept ImportError:\n    from mcp.server.fastmcp import FastMCP\nimport os\nmcp = FastMCP("review")\n@mcp.tool()\ndef echo(value: str) -> str:\n    return "v1:" + value + ":" + str(os.getenv("CAROLE_TEST_SECRET"))\nif __name__ == "__main__":\n    mcp.run(transport="stdio")\n')
    manager = MCPManager()
    keys = [("one", "global", "review"), ("two", "global", "review")]
    try:
        for team in ("one", "two"):
            await manager.connect_stdio_server("review", sys.executable, [str(script)], team_id=team, init_timeout=15)
        first, second = [manager.statuses[key]["tools"][0] for key in keys]
        assert first != second
        assert await ToolRegistry.get(first).handler({"value": "hello", "_context": object()}, "one") == "v1:hello:None"
        old_handler = ToolRegistry.get(first).handler
        script.write_text(script.read_text().replace('"v1:"', '"v2:"'))
        await manager.connect_stdio_server("review", sys.executable, [str(script)], team_id="one", init_timeout=15)
        assert ToolRegistry.get(first).handler is not old_handler
        assert await ToolRegistry.get(first).handler({"value": "hello"}, "one") == "v2:hello:None"
        assert await ToolRegistry.get(second).handler({"value": "hello"}, "two") == "v1:hello:None"
        await manager.disconnect_server(team_id="one", server_name="review")
        assert ToolRegistry.get(first) is None and ToolRegistry.get(second) is not None
    finally:
        for team in ("one", "two"):
            await manager.disconnect_server(team_id=team, server_name="review")


async def test_settings_mask_roundtrip_preserves_keys_and_other_config(monkeypatch):
    from core.api.crud_routes import save_settings, AppSettings
    from unittest.mock import Mock
    original = {"api_keys": {"openai": "real-secret-key"}, "compaction": {"recent_messages_to_keep": 9},
                "browser_automation": {"api_keys": {"browserbase": "real-browser-key"}}}
    save = Mock()
    monkeypatch.setattr("core.llm.config_manager.load_config", lambda: original)
    monkeypatch.setattr("core.llm.config_manager.save_config", save)
    monkeypatch.setattr("core.llm.multi_model_router.llm_router.reload_config", Mock())
    monkeypatch.setattr("core.tools.web_tools.web_tools.reload_config", Mock())
    monkeypatch.setattr("core.tools.voice_stt_tts.voice_service.reload_config", Mock())
    monkeypatch.setattr("core.tools.browser_pool.close_all", AsyncMock())
    await save_settings(AppSettings(api_keys={"openai": "********-key"},
        browser_automation={"api_keys": {"browserbase": "********-key"}}), user={"sub": "owner"})
    saved = save.call_args.args[0]
    assert saved["api_keys"] == original["api_keys"]
    assert saved["browser_automation"]["api_keys"] == original["browser_automation"]["api_keys"]
    assert saved["compaction"] == original["compaction"]


def test_google_tokens_require_owner_and_never_fall_back(tmp_path, monkeypatch):
    import uuid
    from core.api import google_auth_routes as google
    monkeypatch.setattr(google, "CAROLE_HOME_DIR", tmp_path)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    google._save_token(SimpleNamespace(to_json=lambda: '{"token":"private"}'), a)
    assert google._token_path(a).exists()
    assert not google._token_path(b).exists()
    assert google.get_google_credentials() is None


async def test_google_callback_rejects_state_from_another_browser(monkeypatch):
    import time
    from starlette.requests import Request
    from core.api import google_auth_routes as google
    monkeypatch.setattr(google, "_AUTH_SESSIONS", {"attacker-state": {"expires_at": time.time() + 60}})
    request = Request({"type": "http", "headers": [(b"cookie", b"carole_google_state=victim-state")],
        "query_string": b"code=unused&state=attacker-state"})
    result = await google.google_callback(request)
    assert "invalid_state" in result.headers["location"]
    assert "attacker-state" in google._AUTH_SESSIONS
