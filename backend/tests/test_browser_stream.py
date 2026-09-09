import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_browserbase_cdp_with_project_id(monkeypatch):
    """Verify Browserbase CDP endpoint includes both apiKey and projectId when project_id is configured."""
    from core.tools import browser_pool as bp

    with patch("playwright.async_api.async_playwright") as mock_pw_factory, \
         patch("core.llm.config_manager.load_config") as mock_cfg:

        mock_cfg.return_value = {
            "browser_automation": {
                "infrastructure": "browserbase",
                "project_id": "bb_project_99",
                "api_keys": {"browserbase": "bb_key_abc"},
            }
        }

        mock_pw = AsyncMock()
        mock_pw_factory.return_value.start = AsyncMock(return_value=mock_pw)
        mock_chromium = AsyncMock()
        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        mock_chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
        mock_pw.chromium = mock_chromium

        bp._browser = None
        bp._playwright = None

        browser = await bp._ensure_browser()
        assert browser == mock_browser

        # Verify URL parameters
        called_endpoint = mock_chromium.connect_over_cdp.call_args[0][0]
        assert "wss://connect.browserbase.com?" in called_endpoint
        assert "apiKey=bb_key_abc" in called_endpoint
        assert "projectId=bb_project_99" in called_endpoint

        bp._browser = None
        bp._playwright = None


@pytest.mark.asyncio
async def test_browser_use_task_with_browserbase_project_id():
    """Verify _wrap_browser_use_task passes projectId in cdp_url to Browser instance."""
    from core.tools.tool_executor import _wrap_browser_use_task

    mock_cfg = {
        "browser_automation": {
            "provider": "browserbase",
            "project_id": "bb_proj_456",
            "api_keys": {"browserbase": "bb_secret_123"},
        },
        "api_keys": {
            "openai": "sk-test",
            "browserbase": "bb_secret_123",
        },
    }

    mock_agent_instance = AsyncMock()
    mock_agent_instance.run = AsyncMock(return_value="Task executed successfully via Browserbase")

    with patch("core.llm.config_manager.load_config", return_value=mock_cfg), \
         patch("browser_use.Browser") as mock_browser_cls, \
         patch("browser_use.Agent", return_value=mock_agent_instance):

        result = await _wrap_browser_use_task(
            {"task": "Search query", "model": "gpt-4o"},
            team_id="team_test",
        )
        assert "Task executed successfully" in result
        mock_browser_cls.assert_called_once()
        cdp_url = mock_browser_cls.call_args.kwargs.get("cdp_url") or mock_browser_cls.call_args[1].get("cdp_url")
        assert "wss://connect.browserbase.com?" in cdp_url
        assert "apiKey=bb_secret_123" in cdp_url
        assert "projectId=bb_proj_456" in cdp_url


@pytest.mark.asyncio
async def test_browser_act_direct_ref_action(client, owned_browser):
    """Verify POST /api/browser/act resolves DOM element ref and interacts with element."""
    from main import app
    from core.auth.auth_middleware import require_auth

    mock_page = AsyncMock()
    mock_page.url = "https://example.com/ref-test"
    mock_page.title = AsyncMock(return_value="Ref Test")
    mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot_bytes")

    mock_target = AsyncMock()
    mock_target.click = AsyncMock()
    mock_target.fill = AsyncMock()
    mock_target.dispose = AsyncMock()

    app.dependency_overrides[require_auth] = lambda: {"sub": owned_browser["user_id"]}
    try:
        with patch("core.api.browser_routes._get_page", return_value=mock_page), \
             patch("core.tools.browser_tool.browser_tool._target", return_value=(mock_target, True)):

            response = await client.post(
                "/api/browser/act",
                json={"agent_id": owned_browser["agent_id"], "kind": "click", "ref": 42},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["url"] == "https://example.com/ref-test"
            assert "data:image/jpeg;base64," in data["screenshot"]
            mock_target.click.assert_awaited_once()
            mock_target.dispose.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(require_auth, None)


@pytest.mark.asyncio
async def test_browser_act_direct_ssrf_blocking(client, owned_browser):
    """Verify POST /api/browser/act blocks SSRF cloud metadata URLs with HTTP 400."""
    from main import app
    from core.auth.auth_middleware import require_auth

    mock_page = AsyncMock()
    app.dependency_overrides[require_auth] = lambda: {"sub": owned_browser["user_id"]}
    try:
        with patch("core.api.browser_routes._get_page", return_value=mock_page):
            response = await client.post(
                "/api/browser/act",
                json={"agent_id": owned_browser["agent_id"], "kind": "navigate", "url": "http://169.254.169.254/latest/meta-data/"},
            )
            assert response.status_code == 400
            assert "URL access denied" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(require_auth, None)


@pytest.mark.asyncio
async def test_browser_stream_websocket_frame_and_actions(client, owned_browser):
    """Verify WebSocket /api/browser/stream sends frame and executes interactive actions."""
    from starlette.testclient import TestClient
    from main import app

    mock_page = AsyncMock()
    mock_page.url = "https://example.com/live"
    mock_page.title = AsyncMock(return_value="Live Page")
    mock_page.screenshot = AsyncMock(return_value=b"test_ws_frame")
    mock_page.mouse.click = AsyncMock()

    ticket = (await client.post("/api/auth/ws-ticket", headers=owned_browser["headers"])).json()["ticket"]
    with patch("core.api.browser_routes._get_page", return_value=mock_page):
        ws_client = TestClient(app)
        with ws_client.websocket_connect(f"/api/browser/stream?agent_id={owned_browser['agent_id']}&ticket={ticket}") as websocket:
            # First message should be connection confirmation
            conn_msg = websocket.receive_json()
            assert conn_msg["type"] == "connected"

            # Ping/pong check
            websocket.send_text(json.dumps({"type": "ping"}))
            pong_msg = websocket.receive_json()
            assert pong_msg["type"] == "pong"

            # Test interactive coordinate click over WebSocket
            websocket.send_text(json.dumps({
                "type": "act",
                "kind": "coords",
                "x": 250,
                "y": 400,
            }))
            res_msg = websocket.receive_json()
            assert res_msg["type"] == "action_result"
            assert res_msg["status"] == "success"
            assert res_msg["kind"] == "coords"
            mock_page.mouse.click.assert_awaited_with(250.0, 400.0)


@pytest.mark.asyncio
async def test_get_cdp_session_helper():
    """Verify get_cdp_session helper invokes context.new_cdp_session."""
    from core.tools.browser_pool import get_cdp_session

    mock_page = MagicMock()
    mock_cdp = AsyncMock()
    mock_page.context.new_cdp_session = AsyncMock(return_value=mock_cdp)

    with patch("core.tools.browser_pool.get_page", return_value=mock_page):
        session = await get_cdp_session("global")
        assert session == mock_cdp
        mock_page.context.new_cdp_session.assert_awaited_once_with(mock_page)
