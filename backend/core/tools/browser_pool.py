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
from typing import Dict

logger = logging.getLogger("carole.browser_pool")

_playwright = None          # Playwright instance
_browser = None             # Single shared Chromium browser
_contexts: Dict[str, any] = {}   # agent_id → BrowserContext
_lock = asyncio.Lock()


async def _ensure_browser():
    """Launch the shared Playwright browser if not already running."""
    global _playwright, _browser
    if _browser is not None and _browser.is_connected():
        return _browser

    async with _lock:
        # Double-check inside lock
        if _browser is not None and _browser.is_connected():
            return _browser
        try:
            from playwright.async_api import async_playwright
            _playwright = await async_playwright().start()
            _browser = await _playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-extensions",
                ],
            )
            logger.info("🌐 [BrowserPool] Chromium launched (headless=True).")
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

    async with _lock:
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

            ctx = await browser.new_context(
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
            )
            _contexts[agent_id] = ctx
            logger.debug("🌐 [BrowserPool] Created new context for agent %s", agent_id[:8])

        context = _contexts[agent_id]

    pages = context.pages
    if pages:
        return pages[0]
    page = await context.new_page()
    # Intercept console errors so agents get useful debug info
    page.on("pageerror", lambda exc: logger.debug("Browser page error: %s", exc))
    return page


async def close_agent_browser(agent_id: str) -> bool:
    """Close and remove the browser context for a specific agent."""
    async with _lock:
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
    global _browser, _playwright
    async with _lock:
        agent_ids = list(_contexts.keys())

    for agent_id in agent_ids:
        await close_agent_browser(agent_id)

    async with _lock:
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

    logger.info("🌐 [BrowserPool] All browser resources released.")
