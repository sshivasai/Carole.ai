"""
# backend/core/tools/browser_pool.py

Manages the Playwright browser lifecycle for multi-agent concurrent browsing.

Key design decisions:
- One shared Playwright instance, launched lazily on first use.
- One isolated BrowserContext per agent (separate cookies, localStorage, history).
- One persistent Page per agent context (re-used across actions; new page created on demand).
- Thread-safe lock protects all context/page lookups.
- close_agent_browser() allows an agent to cleanly release its session.
- close_all() shuts down the entire browser — called on server shutdown.
"""

import asyncio
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger("carole.browser_pool")

_playwright = None          # Playwright instance
_browser = None             # Single shared Chromium browser
_browser_loop = None        # The event loop in which _browser was started
_contexts: Dict[str, any] = {}   # agent_id → BrowserContext
_lock = None
_lock_loop = None
_headless_override: Optional[bool] = None


def set_headless_mode(headless: Optional[bool]):
    """
    Dynamically set headless mode (True for headless, False for windowed/headed).
    Resetting clears the current browser instance so the next request adopts the new mode.
    """
    global _headless_override, _browser, _playwright
    if _headless_override != headless:
        _headless_override = headless
        _browser = None
        _playwright = None
        _contexts.clear()
        logger.info("🌐 [BrowserPool] Headless mode updated to: %s", headless)


def _get_lock() -> asyncio.Lock:
    """Returns an asyncio.Lock bound to the current running event loop."""
    global _lock, _lock_loop
    current_loop = asyncio.get_running_loop()
    if _lock is None or _lock_loop != current_loop:
        _lock = asyncio.Lock()
        _lock_loop = current_loop
    return _lock


def _is_browser_usable(b, loop) -> bool:
    if b is None:
        return False
    # If mock object (unittest.mock.MagicMock, etc.), accept without event loop check
    if not hasattr(b, "_impl_obj"):
        return True
    channel = getattr(getattr(b, "_impl_obj", None), "_channel", None)
    if channel is None:
        return False
    try:
        return b.is_connected()
    except Exception:
        return False


async def _ensure_browser():
    """Launch the shared Playwright browser if not already running."""
    global _playwright, _browser, _browser_loop
    current_loop = asyncio.get_running_loop()

    if _is_browser_usable(_browser, current_loop):
        _browser_loop = current_loop
        return _browser

    lock = _get_lock()
    async with lock:
        # Double-check inside lock
        if _is_browser_usable(_browser, current_loop):
            _browser_loop = current_loop
            return _browser

        # If browser was created in a dead event loop or disconnected, reset cleanly
        if _browser is not None or _playwright is not None:
            logger.info("🌐 [BrowserPool] Stale browser or disconnected channel. Resetting pool.")
            _contexts.clear()
            _browser = None
            _playwright = None

        try:
            import os
            from playwright.async_api import async_playwright
            from core.llm.config_manager import load_config
            
            _playwright = await async_playwright().start()
            _browser_loop = current_loop
            
            cfg = load_config()
            ba_cfg = cfg.get("browser_automation", {})
            infrastructure = ba_cfg.get("infrastructure") or ba_cfg.get("provider", "local")
            proxy_provider = ba_cfg.get("proxy_provider", "none")
            keys = ba_cfg.get("api_keys", {})
            display_mode = ba_cfg.get("display_mode", "headless")
            
            env_headless = os.environ.get("HEADLESS") or os.environ.get("BROWSER_HEADLESS")
            if _headless_override is not None:
                is_headless = _headless_override
            elif env_headless is not None:
                is_headless = env_headless.strip().lower() not in ("0", "false", "no", "headed", "windowed")
            else:
                is_headless = display_mode != "windowed" and ba_cfg.get("headless", True)
            
            if infrastructure == "browserbase" and keys.get("browserbase"):
                key = keys["browserbase"]
                try:
                    _browser = await _playwright.chromium.connect_over_cdp(f"wss://connect.browserbase.com?apiKey={key}")
                    logger.info("🌐 [BrowserPool] Connected to Browserbase CDP.")
                except Exception as bb_err:
                    logger.warning("⚠️ [BrowserPool] Browserbase connection failed (%s), falling back to local Chromium.", bb_err)
                    _browser = None

            if _browser is None:
                proxy_settings = None
                if (proxy_provider == "scraperapi" or infrastructure == "scraperapi") and keys.get("scraperapi"):
                    proxy_settings = {"server": f"http://scraperapi:{keys['scraperapi']}@proxy-server.scraperapi.com:8001"}
                elif (proxy_provider == "zenrows" or infrastructure == "zenrows") and keys.get("zenrows"):
                    proxy_settings = {"server": f"http://{keys['zenrows']}:@proxy.zenrows.com:8001"}
                
                _browser = await _playwright.chromium.launch(
                    headless=is_headless,
                    proxy=proxy_settings,
                    args=[
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-extensions",
                        # ── Anti-detection / Stealth ──
                        "--disable-blink-features=AutomationControlled",
                        "--disable-infobars",
                        "--window-size=1280,900",
                        "--disable-background-timer-throttling",
                        "--disable-backgrounding-occluded-windows",
                        "--disable-renderer-backgrounding",
                    ],
                )
                logger.info(f"🌐 [BrowserPool] Chromium launched (infra={infrastructure}, headless={is_headless}, proxy={'yes' if proxy_settings else 'no'}).")
        except Exception as e:
            logger.error("✗ [BrowserPool] Failed to launch browser: %s", e)
            raise
    return _browser


MAX_BROWSER_CONTEXTS = 5


async def get_page(agent_id: str):
    """
    Returns an isolated browser Page for the given agent.
    Creates a new BrowserContext and Page if one doesn't exist yet.
    The same page is reused across tool calls to maintain navigation state.
    Limits active contexts to MAX_BROWSER_CONTEXTS to prevent RAM bloat.
    """
    browser = await _ensure_browser()

    lock = _get_lock()
    async with lock:
        if agent_id in _contexts:
            # If the underlying browser reconnected (e.g. BrowserBase timeout),
            # the old context is stale. Evict it so we create a new one.
            if getattr(_contexts[agent_id], "browser", None) != browser:
                logger.warning("🌐 [BrowserPool] Underlying browser changed, evicting stale context for agent %s", agent_id[:8])
                try:
                    await _contexts[agent_id].close()
                except Exception:
                    pass
                _contexts.pop(agent_id, None)

        if agent_id not in _contexts:
            # Enforce max context cap with LRU eviction
            if len(_contexts) >= MAX_BROWSER_CONTEXTS:
                oldest_id = next(iter(_contexts))
                oldest_ctx = _contexts.pop(oldest_id, None)
                if oldest_ctx:
                    try:
                        await oldest_ctx.close()
                        logger.info("🌐 [BrowserPool] Evicted oldest browser context (%s) to maintain cap of %d.", oldest_id[:8], MAX_BROWSER_CONTEXTS)
                    except Exception as e:
                        logger.warning("Browser context eviction error: %s", e)

            async def _create_context_with(target_browser):
                return await target_browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                    timezone_id="America/Chicago",
                    # Accept most common permission types so sites don't block
                    permissions=["notifications"],
                    # ── Anti-detection context options ──
                    device_scale_factor=1,
                    has_touch=False,
                    is_mobile=False,
                    java_script_enabled=True,
                )

            try:
                ctx = await _create_context_with(browser)
            except Exception as e:
                logger.warning("🌐 [BrowserPool] new_context failed on current browser (%s). Recreating browser...", e)
                global _browser, _playwright
                _browser = None
                _playwright = None
                _contexts.clear()
                browser = await _ensure_browser()
                ctx = await _create_context_with(browser)

            # Inject stealth script to remove `navigator.webdriver` flag
            # This is the #1 way Google / Cloudflare detect Playwright
            await ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                // Overwrite the chrome runtime to appear as a regular browser
                window.chrome = { runtime: {} };
                // Overwrite permissions query to always return 'prompt'
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) =>
                    parameters.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : originalQuery(parameters);
            """)
            _contexts[agent_id] = ctx
            logger.debug("🌐 [BrowserPool] Created new stealth context for agent %s", agent_id[:8])

        context = _contexts[agent_id]

    try:
        pages = context.pages
        if pages:
            # Ensure the page itself isn't closed
            if not pages[0].is_closed():
                return pages[0]
        
        page = await context.new_page()
        # Intercept console errors so agents get useful debug info
        page.on("pageerror", lambda exc: logger.debug("Browser page error: %s", exc))
        return page
    except Exception as e:
        logger.warning("🌐 [BrowserPool] Failed to get page from context (possibly closed): %s. Recreating context.", e)
        lock = _get_lock()
        async with lock:
            _contexts.pop(agent_id, None)
        return await get_page(agent_id)


async def get_new_page(agent_id: str):
    """Create a brand-new page (tab) inside the agent's context."""
    # Ensure context is initialized
    await get_page(agent_id)
    
    context = _contexts.get(agent_id)
    if not context:
        raise RuntimeError(f"Context not found for agent {agent_id}")
        
    page = await context.new_page()
    page.on("pageerror", lambda exc: logger.debug("Browser page error: %s", exc))
    return page


async def close_agent_browser(agent_id: str) -> bool:
    """Close and remove the browser context for a specific agent."""
    lock = _get_lock()
    async with lock:
        ctx = _contexts.pop(agent_id, None)
    if ctx:
        try:
            await ctx.close()
            logger.info("🌐 [BrowserPool] Closed context for agent %s", agent_id[:8])
            return True
        except Exception as e:
            logger.warning("BrowserPool close_agent error: %s", e)
    return False


async def get_active_agents() -> list:
    """Returns a list of agent_ids that currently have active browser sessions."""
    return list(_contexts.keys())


async def close_all():
    """Closes all browser contexts and the browser itself. Called on server shutdown."""
    global _browser, _playwright, _browser_loop
    lock = _get_lock()
    async with lock:
        agent_ids = list(_contexts.keys())

    for agent_id in agent_ids:
        await close_agent_browser(agent_id)

    async with lock:
        if _browser:
            try:
                await _browser.close()
                logger.info("🌐 [BrowserPool] Browser closed.")
            except Exception:
                pass
            _browser = None
        if _playwright:
            try:
                await _playwright.stop()
            except Exception:
                pass
            _playwright = None
        _browser_loop = None

    logger.info("🌐 [BrowserPool] All browser resources released.")


import sys
browser_pool = sys.modules[__name__]


