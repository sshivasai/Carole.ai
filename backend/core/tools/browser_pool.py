"""
# backend/core/tools/browser_pool.py

Manages the Playwright browser lifecycle. Provides isolated browser contexts
per agent so multiple agents can browse concurrently without interference.
"""

import asyncio
from typing import Dict, Optional

_browser = None
_contexts: Dict[str, any] = {}  # agent_id -> BrowserContext
_lock = asyncio.Lock()


async def get_browser():
    """Returns the shared Playwright browser instance, launching it if needed."""
    global _browser
    async with _lock:
        if _browser is None:
            try:
                from playwright.async_api import async_playwright
                pw = await async_playwright().start()
                _browser = await pw.chromium.launch(headless=True)
                print("🌐 [BrowserPool] Chromium launched successfully.")
            except Exception as e:
                print(f"✗ [BrowserPool] Failed to launch browser: {e}")
                raise
    return _browser


async def get_page(agent_id: str):
    """Returns an isolated browser page for the given agent.
    Creates a new browser context if one doesn't exist."""
    browser = await get_browser()
    async with _lock:
        if agent_id not in _contexts:
            ctx = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="CaroleAI/1.0 (Headless Chromium)"
            )
            _contexts[agent_id] = ctx
        context = _contexts[agent_id]

    pages = context.pages
    if pages:
        return pages[0]
    return await context.new_page()


async def close_all():
    """Closes all browser contexts and the browser itself."""
    global _browser
    async with _lock:
        for ctx in _contexts.values():
            try:
                await ctx.close()
            except Exception:
                pass
        _contexts.clear()
        if _browser:
            try:
                await _browser.close()
            except Exception:
                pass
            _browser = None
    print("🌐 [BrowserPool] All browser contexts closed.")
