"""
# backend/core/tools/browser_tool.py

Headless browser automation via Playwright. Agents can navigate URLs,
click elements, type text, extract content, and take screenshots.
Screenshots are streamed to the EventBus so humans can watch agents
"surf the web" live in the UI.
"""

import base64
from typing import Dict, Any

from core.chat.event_bus import event_bus


class BrowserTool:
    """Provides browser automation actions. Each action gets an isolated
    page per agent via the browser pool."""

    async def navigate(self, url: str, agent_id: str, agent_name: str, team_id: str) -> str:
        """Navigate to a URL, take a screenshot, and return the page text."""
        try:
            from core.tools.browser_pool import get_page
            page = await get_page(agent_id)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Capture screenshot and stream to EventBus
            screenshot_bytes = await page.screenshot(type="png")
            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            await event_bus.publish(f"team:{team_id}", {
                "type": "browser_screenshot",
                "sender_id": agent_id,
                "sender_name": agent_name,
                "url": url,
                "image_base64": f"data:image/png;base64,{b64}",
            })

            # Extract page text (limited)
            text = await page.inner_text("body")
            text = text[:3000] if len(text) > 3000 else text

            return f"Navigated to {url}. Page title: {await page.title()}\n\nPage text:\n{text}"
        except ImportError:
            return "Error: Playwright is not installed. Run 'pip install playwright && playwright install chromium'."
        except Exception as e:
            return f"Error navigating to {url}: {str(e)}"

    async def screenshot(self, agent_id: str, agent_name: str, team_id: str) -> str:
        """Capture and stream a screenshot of the current page."""
        try:
            from core.tools.browser_pool import get_page
            page = await get_page(agent_id)
            screenshot_bytes = await page.screenshot(type="png")
            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            await event_bus.publish(f"team:{team_id}", {
                "type": "browser_screenshot",
                "sender_id": agent_id,
                "sender_name": agent_name,
                "url": page.url,
                "image_base64": f"data:image/png;base64,{b64}",
            })

            return f"Screenshot captured for {page.url}"
        except Exception as e:
            return f"Error taking screenshot: {str(e)}"

    async def click(self, selector: str, agent_id: str) -> str:
        """Click an element on the page."""
        try:
            from core.tools.browser_pool import get_page
            page = await get_page(agent_id)
            await page.click(selector, timeout=10000)
            return f"Clicked element: {selector}"
        except Exception as e:
            return f"Error clicking '{selector}': {str(e)}"

    async def type_text(self, selector: str, text: str, agent_id: str) -> str:
        """Type text into an input element."""
        try:
            from core.tools.browser_pool import get_page
            page = await get_page(agent_id)
            await page.fill(selector, text, timeout=10000)
            return f"Typed '{text[:50]}' into {selector}"
        except Exception as e:
            return f"Error typing into '{selector}': {str(e)}"

    async def extract_text(self, selector: str, agent_id: str) -> str:
        """Extract text content from a specific element or the whole page."""
        try:
            from core.tools.browser_pool import get_page
            page = await get_page(agent_id)
            if selector:
                text = await page.inner_text(selector)
            else:
                text = await page.inner_text("body")
            text = text[:5000] if len(text) > 5000 else text
            return text
        except Exception as e:
            return f"Error extracting text from '{selector}': {str(e)}"

    async def evaluate_js(self, script: str, agent_id: str) -> str:
        """Run JavaScript in the browser page context."""
        try:
            from core.tools.browser_pool import get_page
            page = await get_page(agent_id)
            result = await page.evaluate(script)
            return str(result)[:3000]
        except Exception as e:
            return f"Error running JS: {str(e)}"


# Singleton
browser_tool = BrowserTool()
