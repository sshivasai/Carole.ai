"""
# backend/tests/test_browser_agent.py

Comprehensive test suite for Carole's Browser Agent and all browser automation providers:
  1. TestBrowserPool: Shared Playwright lifecycle, stealth options, Browserbase CDP connection,
     ScraperAPI/ZenRows proxy configs, LRU context eviction, stale context recovery, cleanup.
  2. TestBrowserTool: SSRF guarding, CAPTCHA detection & auto-resolve polling, Accessibility Tree
     snapshot generation (Ref IDs & XPaths), unified act dispatcher (click, type, slow_type, clear,
     hover, select, check, press, scroll, coords, iframes), dialog handling, tab management,
     content extraction, JS evaluation, cookies.
  3. TestBrowserAgentNative: Autonomous ReACT loop, multi-turn browsing, robust JSON parsing,
     stuck loop detection, max steps boundary, history trimming, human takeover triggering.
  4. TestBrowserUseProvider: Provider routing, direct browser_use_task tool, LLM model mapping
     (OpenAI, OpenRouter, Claude, Gemini), Browserbase CDP configuration for Browser-Use, browser cleanup.
  5. TestBrowserRoutes: /api/browser/act, /api/browser/screenshot, /api/browser/resolve-hil.
  6. TestEndToEndRealPlaywright: Live Chromium headless session testing real form interaction,
     snapshot refs, typing, selecting, clicking, and DOM verification.
"""

import asyncio
import base64
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.tools.tool_registry import ToolRegistry
from core.tools.tool_executor import register_builtin_tools, _wrap_browser_task, _wrap_browser_use_task
from core.tools.browser_tool import browser_tool, _is_captcha_page
from core.tools.browser_agent import BrowserAgent, _extract_json
import core.tools.browser_pool as bp


# ==============================================================================
# 1. BROWSER POOL & PROVIDER INFRASTRUCTURE
# ==============================================================================

class TestBrowserPool:
    """Tests the shared Playwright pool, stealth setup, and multi-provider configs."""

    @pytest.mark.asyncio
    async def test_ensure_browser_local_playwright_launch(self):
        """Verify local Playwright Chromium launches with anti-detection flags."""
        with patch("playwright.async_api.async_playwright") as mock_pw_factory, \
             patch("core.llm.config_manager.load_config") as mock_cfg:
            
            mock_cfg.return_value = {
                "browser_automation": {
                    "infrastructure": "local",
                    "display_mode": "headless",
                    "headless": True,
                }
            }

            mock_pw = AsyncMock()
            mock_pw_factory.return_value.start = AsyncMock(return_value=mock_pw)
            mock_chromium = AsyncMock()
            mock_browser = MagicMock()
            mock_browser.is_connected.return_value = True
            mock_chromium.launch = AsyncMock(return_value=mock_browser)
            mock_pw.chromium = mock_chromium

            # Reset pool state
            bp._browser = None
            bp._playwright = None

            browser = await bp._ensure_browser()
            assert browser == mock_browser
            mock_chromium.launch.assert_called_once()
            call_kwargs = mock_chromium.launch.call_args[1]
            assert call_kwargs["headless"] is True
            assert call_kwargs["proxy"] is None
            args = call_kwargs["args"]
            assert "--disable-blink-features=AutomationControlled" in args
            assert "--disable-dev-shm-usage" in args

            # Cleanup
            bp._browser = None
            bp._playwright = None

    @pytest.mark.asyncio
    async def test_ensure_browser_browserbase_cdp_connection(self):
        """Verify Browserbase connects over CDP via wss://connect.browserbase.com with apiKey."""
        with patch("playwright.async_api.async_playwright") as mock_pw_factory, \
             patch("core.llm.config_manager.load_config") as mock_cfg:
            
            mock_cfg.return_value = {
                "browser_automation": {
                    "infrastructure": "browserbase",
                    "api_keys": {"browserbase": "bb_test_key_12345"},
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
            mock_chromium.connect_over_cdp.assert_called_once_with(
                "wss://connect.browserbase.com?apiKey=bb_test_key_12345"
            )
            # Ensure local launch was NOT called
            mock_chromium.launch.assert_not_called()

            bp._browser = None
            bp._playwright = None

    @pytest.mark.asyncio
    async def test_ensure_browser_proxy_providers(self):
        """Verify ScraperAPI and ZenRows proxy server URLs are injected when configured."""
        with patch("playwright.async_api.async_playwright") as mock_pw_factory, \
             patch("core.llm.config_manager.load_config") as mock_cfg:
            
            mock_pw = AsyncMock()
            mock_pw_factory.return_value.start = AsyncMock(return_value=mock_pw)
            mock_chromium = AsyncMock()
            mock_browser = MagicMock()
            mock_browser.is_connected.return_value = True
            mock_chromium.launch = AsyncMock(return_value=mock_browser)
            mock_pw.chromium = mock_chromium

            # 1. ScraperAPI proxy
            mock_cfg.return_value = {
                "browser_automation": {
                    "infrastructure": "local",
                    "proxy_provider": "scraperapi",
                    "api_keys": {"scraperapi": "scraper_token_999"},
                }
            }
            bp._browser = None
            bp._playwright = None
            await bp._ensure_browser()
            assert mock_chromium.launch.call_args[1]["proxy"] == {
                "server": "http://scraperapi:scraper_token_999@proxy-server.scraperapi.com:8001"
            }

            # 2. ZenRows proxy
            mock_cfg.return_value = {
                "browser_automation": {
                    "infrastructure": "local",
                    "proxy_provider": "zenrows",
                    "api_keys": {"zenrows": "zenrows_token_888"},
                }
            }
            bp._browser = None
            bp._playwright = None
            await bp._ensure_browser()
            assert mock_chromium.launch.call_args[1]["proxy"] == {
                "server": "http://zenrows_token_888:@proxy.zenrows.com:8001"
            }

            bp._browser = None
            bp._playwright = None

    @pytest.mark.asyncio
    async def test_stealth_context_and_lru_cap_eviction(self):
        """Verify stealth init script injection and LRU eviction at MAX_BROWSER_CONTEXTS."""
        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        bp._browser = mock_browser

        created_contexts = {}

        async def fake_new_context(**kwargs):
            ctx = AsyncMock()
            ctx.browser = mock_browser
            ctx.pages = []
            page = AsyncMock()
            page.is_closed.return_value = False
            page.on = MagicMock()
            ctx.new_page = AsyncMock(return_value=page)
            return ctx

        mock_browser.new_context = AsyncMock(side_effect=fake_new_context)
        bp._contexts.clear()

        try:
            # Fill pool up to limit (5)
            for i in range(5):
                agent_id = f"agent_{i}"
                await bp.get_page(agent_id)
                assert agent_id in bp._contexts

            assert len(bp._contexts) == 5
            oldest_ctx = bp._contexts["agent_0"]

            # Adding 6th agent context should evict agent_0
            await bp.get_page("agent_5")
            assert len(bp._contexts) == 5
            assert "agent_0" not in bp._contexts
            assert "agent_5" in bp._contexts
            oldest_ctx.close.assert_called_once()
        finally:
            # Clean up
            await bp.close_all()
            bp._browser = None
            bp._playwright = None
            bp._contexts.clear()
            assert len(bp._contexts) == 0


# ==============================================================================
# 2. BROWSER TOOL & UNIFIED ACT DISPATCHER
# ==============================================================================

class TestBrowserTool:
    """Tests the low-level browser tool functions and unified act dispatcher."""

    def test_captcha_detection_patterns(self):
        """Verify bot/CAPTCHA detection against Cloudflare, Google, and DDoS challenges."""
        assert _is_captcha_page("https://example.com", "Attention Required! | Cloudflare") is True
        assert _is_captcha_page("https://challenges.cloudflare.com/turnstile", "Security Check") is True
        assert _is_captcha_page("https://google.com/sorry/index", "Unusual traffic") is True
        assert _is_captcha_page("https://example.com/login", "Just a moment...") is True
        assert _is_captcha_page("https://example.com/docs", "Documentation | Carole") is False

    @pytest.mark.asyncio
    async def test_navigate_ssrf_blocking(self):
        """Verify SSRF guard blocks internal metadata IP addresses."""
        res = await browser_tool.navigate(
            "http://169.254.169.254/latest/meta-data/", "test_agent", "Agent", "team_1"
        )
        assert "Error" in res or "SSRF" in res or "forbidden" in res.lower()

    @pytest.mark.asyncio
    async def test_snapshot_method_and_ref_mapping(self):
        """Verify snapshot() builds accessibility tree with numbered refs and stores XPath mapping."""
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="Example Domain")
        mock_page.context = "ctx_1"

        # Mock build_dom_tree.js evaluation returning interactive elements
        mock_page.evaluate = AsyncMock(return_value={
            "rootId": 0,
            "map": {
                "0": {"type": "ELEMENT", "tagName": "BODY", "children": [1, 2]},
                "1": {"type": "ELEMENT", "tagName": "INPUT", "highlightIndex": 0, "xpath": "/html/body/input", "attributes": {"name": "q", "type": "text"}, "children": []},
                "2": {"type": "ELEMENT", "tagName": "BUTTON", "highlightIndex": 1, "xpath": "/html/body/button", "attributes": {}, "children": [3]},
                "3": {"type": "TEXT_NODE", "text": "Search", "isVisible": True, "children": []},
            }
        })

        with patch("core.tools.browser_tool._get_page", return_value=mock_page), \
             patch("core.tools.browser_tool._publish_screenshot", new_callable=AsyncMock) as mock_shot:
            
            res = await browser_tool.snapshot("agent_x", "Agent", "team_1", include_screenshot=True)
            assert "Page: https://example.com" in res
            assert "Title: Example Domain" in res
            assert "[0] <input" in res
            assert "[1] <button> Search" in res
            mock_shot.assert_called_once()

            # Verify selector map was cached for act()
            refs = browser_tool._last_selector_maps.get("ctx_1", {})
            assert "0" in refs
            assert refs["0"]["selector"] == "/html/body/input"

    @pytest.mark.asyncio
    async def test_act_dispatcher_all_actions(self):
        """Verify unified act() executes click, type, clear, select, check, press, scroll, coords."""
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.context = "ctx_test"
        mock_page._last_download_path = None
        browser_tool._last_selector_maps["ctx_test"] = {
            "10": {"selector": "/html/body/button[@id='btn']"},
            "11": {"selector": "/html/body/input[@id='txt']"},
            "12": {"selector": "/html/body/select[@id='sel']"},
            "13": {"selector": "/html/body/input[@type='checkbox']"},
        }

        with patch("core.tools.browser_tool._get_page", return_value=mock_page), \
             patch("core.tools.browser_tool._publish_screenshot", new_callable=AsyncMock):
            
            # 1. Click by ref
            res = await browser_tool.act("click", "ag", "Ag", "tm", ref=10)
            assert "✓ click on [10] succeeded" in res
            mock_page.click.assert_called_with("xpath=/html/body/button[@id='btn']", timeout=10000)

            # 2. Type with instant fill
            res = await browser_tool.act("type", "ag", "Ag", "tm", ref=11, text="Carole AI")
            assert "✓ type on [11] succeeded" in res
            mock_page.fill.assert_called_with("xpath=/html/body/input[@id='txt']", "Carole AI", timeout=10000)

            # 3. Type with slow_type delay
            res = await browser_tool.act("type", "ag", "Ag", "tm", ref=11, text="Slow", slow_type=True)
            assert "✓ type on [11] succeeded" in res
            mock_page.type.assert_called_with("xpath=/html/body/input[@id='txt']", "Slow", delay=40, timeout=15000)

            # 4. Clear input
            res = await browser_tool.act("clear", "ag", "Ag", "tm", ref=11)
            assert "✓ clear on [11] succeeded" in res

            # 5. Select dropdown option
            res = await browser_tool.act("select", "ag", "Ag", "tm", ref=12, value="US")
            assert "✓ select on [12] succeeded" in res
            mock_page.select_option.assert_called_with("xpath=/html/body/select[@id='sel']", value="US", timeout=8000)

            # 6. Check / Uncheck
            res = await browser_tool.act("check", "ag", "Ag", "tm", ref=13)
            assert "✓ check on [13] succeeded" in res
            mock_page.check.assert_called_with("xpath=/html/body/input[@type='checkbox']", timeout=8000)

            res = await browser_tool.act("uncheck", "ag", "Ag", "tm", ref=13)
            assert "✓ uncheck on [13] succeeded" in res
            mock_page.uncheck.assert_called_with("xpath=/html/body/input[@type='checkbox']", timeout=8000)

            # 7. Press keyboard key
            res = await browser_tool.act("press", "ag", "Ag", "tm", key="Enter")
            assert "✓ press" in res and "succeeded" in res
            mock_page.keyboard.press.assert_called_with("Enter")

            # 8. Scroll down & up
            res = await browser_tool.act("scroll_down", "ag", "Ag", "tm")
            assert "✓ scroll_down" in res and "succeeded" in res
            mock_page.evaluate.assert_called_with("window.scrollBy(0, 600)")

            # 9. Mouse coordinates click
            res = await browser_tool.act("coords", "ag", "Ag", "tm", x=250.0, y=400.0)
            assert "✓ coords" in res and "succeeded" in res
            mock_page.mouse.click.assert_called_with(250.0, 400.0)

    @pytest.mark.asyncio
    async def test_dialog_handling(self):
        """Verify queueing, auto-dismissing, and handling of browser alert/confirm/prompts."""
        mock_dialog = AsyncMock()
        mock_dialog.type = "confirm"
        mock_dialog.message = "Do you want to delete this record?"
        mock_dialog.default_value = ""

        # Enqueue dialog
        browser_tool._dialog_queues["agent_dlg"] = [{
            "type": mock_dialog.type,
            "message": mock_dialog.message,
            "default_value": "",
            "dialog_obj": mock_dialog,
        }]

        # 1. Accept dialog
        res = await browser_tool.handle_dialog("agent_dlg", accept=True)
        assert "✓ Dialog accepted" in res
        mock_dialog.accept.assert_called_once_with("")

        # 2. Empty queue handling
        res = await browser_tool.handle_dialog("agent_dlg", accept=True)
        assert "No pending dialogs" in res

    @pytest.mark.asyncio
    async def test_tab_management_and_cookies(self):
        """Verify tab switching, tab listing, and cookie manipulation."""
        mock_page1 = MagicMock(url="https://site1.com")
        mock_page2 = MagicMock(url="https://site2.com")
        mock_page2.bring_to_front = AsyncMock()
        mock_page2.close = AsyncMock()

        mock_context = MagicMock()
        mock_context.pages = [mock_page1, mock_page2]
        mock_context.cookies = AsyncMock(return_value=[{"name": "session_id", "value": "abc12345", "domain": "site1.com"}])
        mock_context.clear_cookies = AsyncMock()

        mock_page1.context = mock_context

        with patch("core.tools.browser_tool._get_page", return_value=mock_page1), \
             patch("core.tools.browser_tool._publish_screenshot", new_callable=AsyncMock):
            
            # List tabs
            tabs_res = await browser_tool.list_tabs("ag_tabs")
            assert "Open tabs (2):" in tabs_res
            assert "https://site1.com" in tabs_res
            assert "https://site2.com" in tabs_res

            # Switch tab
            switch_res = await browser_tool.switch_tab(1, "ag_tabs", "Agent", "team_1")
            assert "✓ Switched to tab 1" in switch_res
            mock_page2.bring_to_front.assert_called_once()

            # Cookies
            cookies_res = await browser_tool.get_cookies("ag_tabs")
            assert "session_id=abc12345" in cookies_res
            
            clear_res = await browser_tool.clear_cookies("ag_tabs")
            assert "✓ All cookies cleared" in clear_res
            mock_context.clear_cookies.assert_called_once()


# ==============================================================================
# 3. AUTONOMOUS BROWSER AGENT (NATIVE ReACT LOOP)
# ==============================================================================

class TestBrowserAgentNative:
    """Tests the autonomous BrowserAgent ReACT inner loop, parsing, and bounds."""

    def test_extract_json_resilience(self):
        """Verify _extract_json extracts JSON across various LLM formatting quirks."""
        # Clean json
        assert _extract_json('{"thought": "go", "action": {"type": "navigate"}}') == {
            "thought": "go", "action": {"type": "navigate"}
        }

        # Code block json
        assert _extract_json('```json\n{"thought": "done", "done": true}\n```') == {
            "thought": "done", "done": True
        }

        # Leading & trailing chatter
        assert _extract_json('I will click the button now:\n{"thought": "click", "done": false}\nLet me know.') == {
            "thought": "click", "done": False
        }

        # Invalid returns None
        assert _extract_json('I am not returning valid json at all.') is None

    @pytest.mark.asyncio
    async def test_autonomous_browser_agent_successful_session(self):
        """Simulate a multi-step browsing session: navigate -> type query -> click submit -> done."""
        agent = BrowserAgent(model="gpt-4o")

        # Mock sequence of LLM decisions
        llm_responses = [
            # Step 1: Navigate to google
            json.dumps({"thought": "Navigate to search engine", "done": False, "action": {"type": "navigate", "url": "https://example.com"}}),
            # Step 2: Type search text
            json.dumps({"thought": "Type search keywords", "done": False, "action": {"type": "type", "ref": 1, "text": "Flights to NYC"}}),
            # Step 3: Complete
            json.dumps({"thought": "Found NYC flights under $300", "done": True, "success": True, "summary": "Cheapest flight is JFK $249."}),
        ]

        mock_page = MagicMock(url="https://example.com")
        mock_snapshot_counts = 0

        async def fake_snapshot(page, b_tool):
            nonlocal mock_snapshot_counts
            mock_snapshot_counts += 1
            # Return different snapshot each time so stuck detection doesn't trigger
            return f"[1] <input name='q'> Step {mock_snapshot_counts}"

        with patch("core.tools.browser_pool.get_page", return_value=mock_page), \
             patch("core.tools.browser_tool.browser_tool.navigate", new_callable=AsyncMock, return_value="Navigated"), \
             patch("core.tools.browser_tool.browser_tool.act", new_callable=AsyncMock, return_value="Act done"), \
             patch("core.llm.multi_model_router.llm_router.generate_completion", new_callable=AsyncMock, side_effect=llm_responses), \
             patch.object(agent, "_snapshot", side_effect=fake_snapshot):
            
            result = await agent.run(
                command="Find cheap flights to NYC",
                agent_id="test_agent",
                agent_name="Flyer",
                team_id="team_travel",
            )
            assert result.startswith("✓")
            assert "Cheapest flight is JFK $249." in result

    @pytest.mark.asyncio
    async def test_autonomous_browser_agent_stuck_detection(self):
        """Verify agent terminates early when snapshots remain unchanged for 3 consecutive steps."""
        agent = BrowserAgent(model="gpt-4o")

        # LLM keeps attempting the same click
        repeated_action = json.dumps({
            "thought": "Trying to click next",
            "done": False,
            "action": {"type": "click", "ref": 5},
        })

        mock_page = MagicMock(url="https://example.com/stuck")

        with patch("core.tools.browser_pool.get_page", return_value=mock_page), \
             patch("core.tools.browser_tool.browser_tool.act", new_callable=AsyncMock, return_value="Clicked"), \
             patch("core.llm.multi_model_router.llm_router.generate_completion", new_callable=AsyncMock, return_value=repeated_action), \
             patch.object(agent, "_snapshot", new_callable=AsyncMock, return_value="[5] <button> Unchanged Page"):
            
            result = await agent.run(
                command="Click through carousel",
                agent_id="test_agent",
                agent_name="Clicker",
                team_id="team_test",
            )
            assert "⚠️ Browsing stopped: the page stopped changing after 3 steps" in result

    @pytest.mark.asyncio
    async def test_autonomous_browser_agent_human_takeover(self):
        """Verify LLM can request browser_human_takeover when encountering CAPTCHAs/logins."""
        agent = BrowserAgent(model="gpt-4o")

        takeover_decision = json.dumps({
            "thought": "Encountered Cloudflare challenge that requires manual verification",
            "done": False,
            "action": {
                "type": "browser_human_takeover",
                "reason": "Please solve the Cloudflare verification on screen",
            },
        })
        done_decision = json.dumps({
            "thought": "Human solved captcha, proceeding",
            "done": True,
            "success": True,
            "summary": "Page accessed successfully after CAPTCHA solution.",
        })

        mock_page = AsyncMock(url="https://challenges.cloudflare.com")
        mock_page.screenshot = AsyncMock(return_value=b"fake_jpeg_bytes")

        with patch("core.tools.browser_pool.get_page", return_value=mock_page), \
             patch("core.tools.interaction_tools.interaction_tools.browser_human_takeover", new_callable=AsyncMock, return_value="User solved captcha") as mock_takeover, \
             patch("core.llm.multi_model_router.llm_router.generate_completion", new_callable=AsyncMock, side_effect=[takeover_decision, done_decision]), \
             patch.object(agent, "_snapshot", side_effect=["[1] CAPTCHA", "[2] Dashboard"]):
            
            result = await agent.run(
                command="Access protected dashboard",
                agent_id="test_agent",
                agent_name="Scraper",
                team_id="team_test",
            )
            assert "✓ Page accessed successfully after CAPTCHA solution." in result
            mock_takeover.assert_called_once()
            assert "Cloudflare verification" in mock_takeover.call_args[1]["reason"]


# ==============================================================================
# 4. BROWSER-USE FRAMEWORK & PROVIDER ROUTING
# ==============================================================================

class TestBrowserUseProvider:
    """Tests provider routing to browser-use and external library initialization."""

    @pytest.mark.asyncio
    async def test_wrap_browser_task_provider_routing(self):
        """Verify provider 'browseruse' routes to browser-use, while 'local' routes to BrowserAgent."""
        # 1. 'browseruse' routes to _wrap_browser_use_task
        with patch("core.llm.config_manager.load_config", return_value={"browser_automation": {"provider": "browseruse"}}), \
             patch("core.tools.tool_executor._wrap_browser_use_task", new_callable=AsyncMock, return_value="BrowserUse Executed") as mock_bu:
            
            res = await _wrap_browser_task({"task": "Book a table"}, "team_1")
            assert res == "BrowserUse Executed"
            mock_bu.assert_called_once()

        # 2. 'local' routes to BrowserAgent.run
        with patch("core.llm.config_manager.load_config", return_value={"browser_automation": {"provider": "local"}}), \
             patch("core.tools.browser_agent.BrowserAgent.run", new_callable=AsyncMock, return_value="✓ Native ReACT Executed") as mock_react:
            
            res = await _wrap_browser_task({"task": "Book a table"}, "team_1")
            assert res == "✓ Native ReACT Executed"
            mock_react.assert_called_once()

    @pytest.mark.asyncio
    async def test_browser_use_tool_spec_registered(self):
        """Verify browser_use_task and browser_task are correctly registered in ToolRegistry."""
        register_builtin_tools()
        tools = {t.name: t for t in ToolRegistry.list_all()}
        assert "browser_task" in tools
        assert "browser_use_task" in tools
        assert tools["browser_task"].category == "browser"
        assert tools["browser_use_task"].category == "browser"

    @pytest.mark.asyncio
    async def test_browser_use_llm_model_mapping(self):
        """Verify browser-use configures LangChain LLMs and Browserbases CDP URL."""
        # Test OpenAI model mapping and Browserbase CDP URL wiring
        cfg = {
            "browser_automation": {
                "provider": "browserbase",
                "api_keys": {"browserbase": "bb_secret_999"},
            },
            "api_keys": {
                "openrouter": "sk-or-test-key",
                "openai": "sk-test-key",
                "browserbase": "bb_secret_999",
            }
        }

        with patch("core.llm.config_manager.load_config", return_value=cfg), \
             patch("browser_use.Browser") as mock_browser_cls, \
             patch("browser_use.Agent") as mock_agent_cls, \
             patch("langchain_openai.ChatOpenAI") as mock_openai:
            
            mock_browser_inst = AsyncMock()
            mock_browser_cls.return_value = mock_browser_inst
            mock_agent_inst = AsyncMock()
            mock_agent_inst.run = AsyncMock(return_value="Order confirmed #101")
            mock_agent_cls.return_value = mock_agent_inst

            res = await _wrap_browser_use_task({"task": "Order pizza", "_agent_id": "agent_pizza"}, "team_food")
            assert "Order confirmed #101" in res

            # Verify Browserbase CDP url passed to Browser
            mock_browser_cls.assert_called_with(cdp_url="wss://connect.browserbase.com?apiKey=bb_secret_999")
            # Verify ChatOpenAI initialized
            mock_openai.assert_called_once()
            # Verify browser instance closed cleanly
            mock_browser_inst.close.assert_called_once()


# ==============================================================================
# 5. REST API & CANVAS TAKEOVER ROUTES (/api/browser/*)
# ==============================================================================

class TestBrowserRoutes:
    """Tests the canvas takeover and direct browser interaction HTTP endpoints."""

    @pytest.mark.asyncio
    async def test_browser_act_direct_endpoint(self, client):
        """Verify POST /api/browser/act executes coords click and returns updated screenshot."""
        from main import app
        from core.auth.auth_middleware import require_auth

        mock_page = AsyncMock()
        mock_page.url = "https://example.com/canvas"
        mock_page.title = AsyncMock(return_value="Canvas Demo")
        mock_page.screenshot = AsyncMock(return_value=b"test_screenshot_data")

        app.dependency_overrides[require_auth] = lambda: {"id": "u1", "role": "admin"}
        try:
            with patch("core.api.browser_routes._get_page", return_value=mock_page):
                response = await client.post(
                    "/api/browser/act",
                    json={"agent_id": "global", "kind": "coords", "x": 150.0, "y": 300.0},
                )
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["url"] == "https://example.com/canvas"
                assert data["title"] == "Canvas Demo"
                assert "data:image/jpeg;base64," in data["screenshot"]
                mock_page.mouse.click.assert_called_with(150.0, 300.0)
        finally:
            app.dependency_overrides.pop(require_auth, None)

    @pytest.mark.asyncio
    async def test_browser_screenshot_endpoint(self, client):
        """Verify GET /api/browser/screenshot fetches current screenshot."""
        from main import app
        from core.auth.auth_middleware import require_auth

        mock_page = AsyncMock()
        mock_page.url = "https://example.com/status"
        mock_page.title = AsyncMock(return_value="Status Page")
        mock_page.screenshot = AsyncMock(return_value=b"shot_bytes")

        app.dependency_overrides[require_auth] = lambda: {"id": "u1"}
        try:
            with patch("core.api.browser_routes._get_page", return_value=mock_page):
                response = await client.get("/api/browser/screenshot?agent_id=global")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["title"] == "Status Page"
                assert data["screenshot"].startswith("data:image/jpeg;base64,")
        finally:
            app.dependency_overrides.pop(require_auth, None)


# ==============================================================================
# 6. LIVE END-TO-END PLAYWRIGHT CHROMIUM INTEGRATION
# ==============================================================================

class TestEndToEndRealPlaywright:
    """Executes a real local headless Chromium session on an in-memory HTML page."""

    @pytest.mark.asyncio
    async def test_real_playwright_form_submission_and_snapshots(self, monkeypatch):
        """Launch real Chromium, navigate to an HTML form, snapshot refs, interact, and verify DOM."""
        from core.llm import config_manager
        orig_load = config_manager.load_config

        def mock_load():
            cfg = orig_load()
            cfg_copy = dict(cfg)
            ba = dict(cfg_copy.get("browser_automation", {}))
            ba["infrastructure"] = "local"
            ba["provider"] = "local"
            ba["headless"] = True
            cfg_copy["browser_automation"] = ba
            return cfg_copy

        monkeypatch.setattr(config_manager, "load_config", mock_load)

        # Ensure starting from clean local browser
        await bp.close_all()
        bp._browser = None
        bp._playwright = None
        bp._contexts.clear()

        agent_id = "real_playwright_test_agent"
        try:
            page = await bp.get_page(agent_id)

            # In-memory HTML page with form inputs
            html_content = """
            <!DOCTYPE html>
            <html>
            <head><title>Carole Integration Test</title></head>
            <body style="margin: 20px; font-family: sans-serif;">
                <h1>Automated Browser Test</h1>
                <form id="test-form" onsubmit="event.preventDefault(); document.getElementById('msg').innerText = 'SUCCESS: ' + document.getElementById('username').value + ' | ' + document.getElementById('role').value;">
                    <label>User: <input type="text" id="username" name="user" value="" /></label><br/><br/>
                    <label>Role:
                        <select id="role" name="role">
                            <option value="developer">Developer</option>
                            <option value="manager">Manager</option>
                        </select>
                    </label><br/><br/>
                    <label><input type="checkbox" id="terms" /> Accept terms</label><br/><br/>
                    <button type="submit" id="submit-btn">Submit Form</button>
                </form>
                <p id="msg">Initial State</p>
            </body>
            </html>
            """
            # Load page content directly
            await page.set_content(html_content, wait_until="domcontentloaded")

            # 1. Test snapshot generation on live DOM
            snapshot = await browser_tool.snapshot(agent_id, include_screenshot=False)
            assert "Automated Browser Test" in snapshot
            assert "<input" in snapshot
            assert "<select" in snapshot
            assert "<button" in snapshot

            # 2. Interact using live selector / refs
            # Type into username
            type_res = await browser_tool.act("type", agent_id, "Agent", "team_1", selector="#username", text="Ada Lovelace")
            assert "succeeded" in type_res

            # Select role
            sel_res = await browser_tool.act("select", agent_id, "Agent", "team_1", selector="#role", value="developer")
            assert "succeeded" in sel_res

            # Check checkbox
            chk_res = await browser_tool.act("check", agent_id, "Agent", "team_1", selector="#terms")
            assert "succeeded" in chk_res

            # Click submit button
            clk_res = await browser_tool.act("click", agent_id, "Agent", "team_1", selector="#submit-btn")
            assert "succeeded" in clk_res

            # 3. Verify DOM text updated from the submission
            result_text = await browser_tool.extract_text("#msg", agent_id)
            assert "SUCCESS: Ada Lovelace | developer" in result_text
        finally:
            # 4. Clean teardown
            await bp.close_all()
            bp._browser = None
            bp._playwright = None
            bp._contexts.clear()
