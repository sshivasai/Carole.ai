"""
# backend/core/tools/browser_tool.py

Full-featured headless browser automation via Playwright.

Agents get an isolated browser context (separate cookies / session) and can:
  - Navigate to URLs and read page content
  - Take and stream screenshots to the team EventBus (visible in UI)
  - Click elements by CSS selector, text, or aria-label
  - Type into input fields, fill forms, press keyboard keys
  - Scroll the page or specific elements
  - Hover over elements
  - Select dropdown options
  - Extract text / HTML from any element
  - Evaluate arbitrary JavaScript
  - Wait for elements or network idle
  - Manage multiple tabs (open, switch, close)
  - Go back / forward in browser history
  - Get page metadata (URL, title, cookies, local storage)
  - Close their own browser session when done

All screenshots are automatically streamed to the team EventBus so humans
can watch agents browse in real-time from the frontend.
"""

import asyncio
import base64
import json
import logging

from core.chat.event_bus import event_bus

logger = logging.getLogger("carole.browser")

# Maximum characters to return for page text (to keep token counts manageable)
MAX_TEXT_CHARS = 100000
MAX_HTML_CHARS = 100000

async def _get_page(agent_id: str):
    """Helper: get the current page for an agent."""
    from core.tools.browser_pool import get_page
    return await get_page(agent_id)


async def _publish_screenshot(page, agent_id: str, agent_name: str, team_id: str, label: str = ""):
    """Capture a screenshot and broadcast it to the team topic."""
    try:
        screenshot_bytes = await page.screenshot(type="jpeg", quality=60, full_page=False)
        b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        await event_bus.publish(f"team:{team_id}", {
            "type": "browser_screenshot",
            "sender_id": agent_id,
            "sender_name": agent_name,
            "url": page.url,
            "label": label,
            "image_base64": f"data:image/jpeg;base64,{b64}",
        })
    except Exception as e:
        logger.warning("Failed to capture screenshot: %s", e)


class BrowserTool:
    """Provides a complete browser automation suite.
    Each method corresponds to a registered agent tool."""

    # ------------------------------------------------------------------ #
    # Navigation
    # ------------------------------------------------------------------ #

    async def navigate(self, url: str, agent_id: str, agent_name: str, team_id: str,
                       wait_until: str = "domcontentloaded") -> str:
        """Navigate to a URL and return the page title + visible text.
        Waits for networkidle after initial load to handle JS-rendered pages."""
        try:
            page = await _get_page(agent_id)
            response = await page.goto(url, wait_until=wait_until, timeout=30_000)
            status = response.status if response else "unknown"

            # Wait for network idle so JS-rendered forms/SPAs fully load
            try:
                await page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass  # Best-effort; some pages never go fully idle

            await _publish_screenshot(page, agent_id, agent_name, team_id, f"Navigated to {url}")

            title = await page.title()
            html_content = await page.content()
            
            try:
                import markdownify
                text = markdownify.markdownify(html_content, heading_style="ATX", strip=["script", "style", "nav", "footer", "header"])
            except ImportError:
                text = await page.inner_text("body")
            
            if len(text) > MAX_TEXT_CHARS:
                text = text[:MAX_TEXT_CHARS] + "\n\n[Content truncated due to length...]"
            # Detect iframes so the agent knows the page has embedded content
            iframe_count = await page.evaluate("document.querySelectorAll('iframe').length")
            iframe_hint = ""
            if iframe_count > 0:
                iframe_hint = (
                    f"\n⚠️ This page contains {iframe_count} iframe(s). "
                    f"Form fields may be inside an iframe. Use browser_get_interactive_elements "
                    f"to discover all inputs (including inside iframes).\n"
                )

            return (
                f"✓ Navigated to {url}\n"
                f"  Status: {status} | Title: {title}{iframe_hint}\n\n"
                f"Page text:\n{text}"
            )
        except ImportError:
            return "Error: Playwright not installed. Run: pip install playwright && playwright install chromium"
        except Exception as e:
            return f"Error navigating to '{url}': {str(e)}"

    async def go_back(self, agent_id: str, agent_name: str, team_id: str) -> str:
        """Navigate back in the browser history."""
        try:
            page = await _get_page(agent_id)
            await page.go_back(timeout=10_000)
            await _publish_screenshot(page, agent_id, agent_name, team_id, "Go back")
            return f"✓ Went back. Now at: {page.url}"
        except Exception as e:
            return f"Error going back: {str(e)}"

    async def go_forward(self, agent_id: str, agent_name: str, team_id: str) -> str:
        """Navigate forward in the browser history."""
        try:
            page = await _get_page(agent_id)
            await page.go_forward(timeout=10_000)
            await _publish_screenshot(page, agent_id, agent_name, team_id, "Go forward")
            return f"✓ Went forward. Now at: {page.url}"
        except Exception as e:
            return f"Error going forward: {str(e)}"

    async def reload(self, agent_id: str, agent_name: str, team_id: str) -> str:
        """Reload the current page."""
        try:
            page = await _get_page(agent_id)
            await page.reload(wait_until="domcontentloaded", timeout=15_000)
            await _publish_screenshot(page, agent_id, agent_name, team_id, "Page reloaded")
            return f"✓ Page reloaded: {page.url}"
        except Exception as e:
            return f"Error reloading: {str(e)}"

    async def get_current_url(self, agent_id: str) -> str:
        """Return the current page URL."""
        try:
            page = await _get_page(agent_id)
            return f"Current URL: {page.url}"
        except Exception as e:
            return f"Error getting URL: {str(e)}"

    # ------------------------------------------------------------------ #
    # Screenshots & Visual Analysis
    # ------------------------------------------------------------------ #

    async def screenshot(self, agent_id: str, agent_name: str, team_id: str,
                         full_page: bool = False) -> str:
        """Capture a screenshot of the current page and stream it to the UI."""
        try:
            page = await _get_page(agent_id)
            screenshot_bytes = await page.screenshot(type="jpeg", quality=60, full_page=full_page)
            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            await event_bus.publish(f"team:{team_id}", {
                "type": "browser_screenshot",
                "sender_id": agent_id,
                "sender_name": agent_name,
                "url": page.url,
                "label": "Manual screenshot",
                "image_base64": f"data:image/jpeg;base64,{b64}",
            })
            return f"✓ Screenshot captured for {page.url} ({'full page' if full_page else 'viewport'})"
        except Exception as e:
            return f"Error taking screenshot: {str(e)}"

    async def screenshot_element(self, selector: str, agent_id: str, agent_name: str, team_id: str) -> str:
        """Take a screenshot of a specific element."""
        try:
            page = await _get_page(agent_id)
            element = await page.query_selector(selector)
            if not element:
                return f"Error: Element '{selector}' not found."
            screenshot_bytes = await element.screenshot(type="jpeg", quality=60)
            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            await event_bus.publish(f"team:{team_id}", {
                "type": "browser_screenshot",
                "sender_id": agent_id,
                "sender_name": agent_name,
                "url": page.url,
                "label": f"Element: {selector}",
                "image_base64": f"data:image/jpeg;base64,{b64}",
            })
            return f"✓ Screenshot taken of element '{selector}'"
        except Exception as e:
            return f"Error screenshotting element '{selector}': {str(e)}"

    # ------------------------------------------------------------------ #
    # Interaction
    # ------------------------------------------------------------------ #

    async def click(self, selector: str, agent_id: str, agent_name: str = "", team_id: str = "") -> str:
        """Click an element by CSS selector. Automatically searches iframes if not found on main page."""
        try:
            page = await _get_page(agent_id)
            try:
                await page.click(selector, timeout=10_000)
            except Exception:
                # Fallback: search inside iframes
                clicked = await self._try_in_frames(page, "click", selector)
                if not clicked:
                    raise
            if team_id:
                await _publish_screenshot(page, agent_id, agent_name, team_id, f"Clicked: {selector}")
            return f"✓ Clicked element: {selector}"
        except Exception as e:
            return f"Error clicking '{selector}': {str(e)}"

    async def click_text(self, text: str, agent_id: str, agent_name: str = "", team_id: str = "") -> str:
        """Click an element by its visible text content."""
        try:
            page = await _get_page(agent_id)
            await page.get_by_text(text, exact=False).first.click(timeout=10_000)
            if team_id:
                await _publish_screenshot(page, agent_id, agent_name, team_id, f"Clicked text: {text}")
            return f"✓ Clicked element with text: '{text}'"
        except Exception as e:
            return f"Error clicking text '{text}': {str(e)}"

    async def type_text(self, selector: str, text: str, agent_id: str,
                        clear_first: bool = True) -> str:
        """Type text into an input element. Automatically searches iframes if not found on main page."""
        try:
            page = await _get_page(agent_id)
            try:
                if clear_first:
                    await page.fill(selector, text, timeout=10_000)
                else:
                    await page.type(selector, text, delay=30, timeout=10_000)
            except Exception:
                # Fallback: search inside iframes
                filled = await self._try_in_frames(page, "fill" if clear_first else "type", selector, text)
                if not filled:
                    raise
            return f"✓ Typed '{text[:80]}{'...' if len(text) > 80 else ''}' into {selector}"
        except Exception as e:
            return f"Error typing into '{selector}': {str(e)}"

    async def press_key(self, key: str, agent_id: str) -> str:
        """Press a keyboard key (e.g. 'Enter', 'Tab', 'Escape', 'ArrowDown')."""
        try:
            page = await _get_page(agent_id)
            await page.keyboard.press(key)
            return f"✓ Pressed key: {key}"
        except Exception as e:
            return f"Error pressing key '{key}': {str(e)}"

    async def hover(self, selector: str, agent_id: str, agent_name: str = "", team_id: str = "") -> str:
        """Hover over an element to trigger tooltips or dropdowns."""
        try:
            page = await _get_page(agent_id)
            await page.hover(selector, timeout=10_000)
            if team_id:
                await _publish_screenshot(page, agent_id, agent_name, team_id, f"Hover: {selector}")
            return f"✓ Hovered over: {selector}"
        except Exception as e:
            return f"Error hovering over '{selector}': {str(e)}"

    async def select_option(self, selector: str, value: str, agent_id: str) -> str:
        """Select an option in a <select> dropdown by value or label."""
        try:
            page = await _get_page(agent_id)
            # Try by value first, then by label
            try:
                selected = await page.select_option(selector, value=value, timeout=8_000)
            except Exception:
                selected = await page.select_option(selector, label=value, timeout=8_000)
            return f"✓ Selected '{value}' in {selector} (selected: {selected})"
        except Exception as e:
            return f"Error selecting option in '{selector}': {str(e)}"

    async def check_checkbox(self, selector: str, checked: bool, agent_id: str) -> str:
        """Check or uncheck a checkbox."""
        try:
            page = await _get_page(agent_id)
            if checked:
                await page.check(selector, timeout=8_000)
            else:
                await page.uncheck(selector, timeout=8_000)
            state = "checked" if checked else "unchecked"
            return f"✓ Checkbox '{selector}' {state}"
        except Exception as e:
            return f"Error on checkbox '{selector}': {str(e)}"

    async def scroll(self, direction: str, amount: int, agent_id: str,
                     selector: str = "") -> str:
        """Scroll the page (or a specific element) up/down/left/right by pixels."""
        try:
            page = await _get_page(agent_id)
            dx = dy = 0
            if direction == "down":
                dy = amount
            elif direction == "up":
                dy = -amount
            elif direction == "right":
                dx = amount
            elif direction == "left":
                dx = -amount
            else:
                return f"Error: Unknown scroll direction '{direction}'. Use: up/down/left/right."

            if selector:
                await page.evaluate(
                    f"document.querySelector('{selector}')?.scrollBy({dx}, {dy})"
                )
            else:
                await page.evaluate(f"window.scrollBy({dx}, {dy})")
            return f"✓ Scrolled {direction} by {amount}px"
        except Exception as e:
            return f"Error scrolling: {str(e)}"

    async def scroll_to_element(self, selector: str, agent_id: str) -> str:
        """Scroll an element into view."""
        try:
            page = await _get_page(agent_id)
            element = await page.query_selector(selector)
            if not element:
                return f"Error: Element '{selector}' not found."
            await element.scroll_into_view_if_needed()
            return f"✓ Scrolled to element: {selector}"
        except Exception as e:
            return f"Error scrolling to element: {str(e)}"

    # ------------------------------------------------------------------ #
    # Content Extraction
    # ------------------------------------------------------------------ #

    async def extract_text(self, selector: str, agent_id: str) -> str:
        """Extract visible text from a specific element or the whole page body."""
        try:
            page = await _get_page(agent_id)
            target = selector if selector else "body"
            text = await page.inner_text(target, timeout=8_000)
            text = text[:MAX_TEXT_CHARS]
            return text if text else "No text found."
        except Exception as e:
            return f"Error extracting text from '{selector}': {str(e)}"

    async def extract_html(self, selector: str, agent_id: str) -> str:
        """Extract the raw HTML of a specific element or the whole document."""
        try:
            page = await _get_page(agent_id)
            if selector:
                element = await page.query_selector(selector)
                if not element:
                    return f"Error: Element '{selector}' not found."
                html = await element.inner_html()
            else:
                html = await page.content()
            return html[:MAX_HTML_CHARS]
        except Exception as e:
            return f"Error extracting HTML from '{selector}': {str(e)}"

    async def get_attribute(self, selector: str, attribute: str, agent_id: str) -> str:
        """Get the value of an attribute from an element (e.g. href, src, value)."""
        try:
            page = await _get_page(agent_id)
            element = await page.query_selector(selector)
            if not element:
                return f"Error: Element '{selector}' not found."
            value = await element.get_attribute(attribute)
            return f"Attribute '{attribute}' of '{selector}': {value}"
        except Exception as e:
            return f"Error getting attribute: {str(e)}"

    async def find_elements(self, selector: str, agent_id: str, limit: int = 20) -> str:
        """Find all elements matching a CSS selector and return their text/attributes."""
        try:
            page = await _get_page(agent_id)
            elements = await page.query_selector_all(selector)
            if not elements:
                return f"No elements found matching '{selector}'."

            results = []
            for i, el in enumerate(elements[:limit]):
                text = (await el.inner_text())[:100]
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                href = await el.get_attribute("href") or ""
                results.append(f"  [{i}] <{tag}> {text!r}" + (f" href={href!r}" if href else ""))

            header = f"Found {len(elements)} element(s) matching '{selector}' (showing {min(limit, len(elements))}):\n"
            return header + "\n".join(results)
        except Exception as e:
            return f"Error finding elements: {str(e)}"

    async def get_page_metadata(self, agent_id: str) -> str:
        """Return the current URL, title, and meta description."""
        try:
            page = await _get_page(agent_id)
            title = await page.title()
            url = page.url
            description = await page.evaluate(
                "document.querySelector('meta[name=\"description\"]')?.content || ''"
            )
            links_count = await page.evaluate("document.querySelectorAll('a').length")
            images_count = await page.evaluate("document.querySelectorAll('img').length")
            return (
                f"Page Metadata:\n"
                f"  URL: {url}\n"
                f"  Title: {title}\n"
                f"  Description: {description}\n"
                f"  Links: {links_count} | Images: {images_count}"
            )
        except Exception as e:
            return f"Error getting page metadata: {str(e)}"

    async def get_all_links(self, agent_id: str, limit: int = 30) -> str:
        """Extract all hyperlinks from the current page."""
        try:
            page = await _get_page(agent_id)
            links = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
                    text: a.innerText.trim().slice(0, 80),
                    href: a.href
                }))
            """)
            if not links:
                return "No links found on this page."
            lines = [f"  [{i}] {l['text']!r} → {l['href']}" for i, l in enumerate(links[:limit])]
            return f"Found {len(links)} links (showing {min(limit, len(links))}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error getting links: {str(e)}"

    # ------------------------------------------------------------------ #
    # JavaScript Execution
    # ------------------------------------------------------------------ #

    async def evaluate_js(self, script: str, agent_id: str) -> str:
        """Execute JavaScript in the browser and return the result."""
        try:
            page = await _get_page(agent_id)
            result = await page.evaluate(script)
            result_str = json.dumps(result, default=str) if not isinstance(result, str) else result
            return result_str[:3000]
        except Exception as e:
            return f"Error running JS: {str(e)}"

    # ------------------------------------------------------------------ #
    # Waiting
    # ------------------------------------------------------------------ #

    async def wait_for_selector(self, selector: str, agent_id: str, timeout_ms: int = 10000) -> str:
        """Wait until a CSS selector appears in the DOM."""
        try:
            page = await _get_page(agent_id)
            await page.wait_for_selector(selector, timeout=timeout_ms)
            return f"✓ Element '{selector}' appeared in DOM."
        except Exception as e:
            return f"Timeout/error waiting for '{selector}': {str(e)}"

    async def wait_for_navigation(self, agent_id: str, timeout_ms: int = 10000) -> str:
        """Wait for a navigation event to complete (e.g. after clicking a link)."""
        try:
            page = await _get_page(agent_id)
            await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            return f"✓ Navigation complete. Now at: {page.url}"
        except Exception as e:
            return f"Timeout/error waiting for navigation: {str(e)}"

    async def wait_ms(self, ms: int, agent_id: str) -> str:
        """Wait for a specified number of milliseconds (max 10 seconds)."""
        ms = min(ms, 10_000)
        await asyncio.sleep(ms / 1000)
        return f"✓ Waited {ms}ms."

    # ------------------------------------------------------------------ #
    # Cookies & Storage
    # ------------------------------------------------------------------ #

    async def get_cookies(self, agent_id: str) -> str:
        """Get all cookies for the current browser context."""
        try:
            page = await _get_page(agent_id)
            cookies = await page.context.cookies()
            if not cookies:
                return "No cookies set."
            lines = [f"  {c['name']}={c['value'][:40]} (domain={c.get('domain', '')})"
                     for c in cookies[:30]]
            return f"Cookies ({len(cookies)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error getting cookies: {str(e)}"

    async def clear_cookies(self, agent_id: str) -> str:
        """Clear all cookies for the agent's browser context."""
        try:
            page = await _get_page(agent_id)
            await page.context.clear_cookies()
            return "✓ All cookies cleared."
        except Exception as e:
            return f"Error clearing cookies: {str(e)}"

    # ------------------------------------------------------------------ #
    # Tab Management
    # ------------------------------------------------------------------ #

    async def open_new_tab(self, url: str, agent_id: str, agent_name: str, team_id: str) -> str:
        """Open a URL in a new browser tab. Waits for networkidle for JS-rendered pages."""
        try:
            from core.tools.browser_pool import get_page
            page = await get_page(agent_id)
            new_page = await page.context.new_page()
            await new_page.goto(url, wait_until="domcontentloaded", timeout=30_000)

            # Wait for network idle so JS-rendered forms fully load
            try:
                await new_page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass  # Best-effort

            await _publish_screenshot(new_page, agent_id, agent_name, team_id, f"New tab: {url}")

            # Detect iframes
            iframe_count = await new_page.evaluate("document.querySelectorAll('iframe').length")
            iframe_hint = ""
            if iframe_count > 0:
                iframe_hint = (
                    f"\n⚠️ This page contains {iframe_count} iframe(s). "
                    f"Form fields may be inside an iframe. Use browser_get_interactive_elements "
                    f"to discover all inputs (including inside iframes)."
                )

            return f"✓ Opened new tab at {url} (now on tab index {len(page.context.pages) - 1}){iframe_hint}"
        except Exception as e:
            return f"Error opening new tab: {str(e)}"

    async def switch_tab(self, index: int, agent_id: str, agent_name: str, team_id: str) -> str:
        """Switch to a browser tab by index."""
        try:
            page = await _get_page(agent_id)
            pages = page.context.pages
            if index < 0 or index >= len(pages):
                return f"Error: Tab index {index} is out of range (0–{len(pages)-1})."
            target = pages[index]
            await target.bring_to_front()
            await _publish_screenshot(target, agent_id, agent_name, team_id, f"Switched to tab {index}")
            return f"✓ Switched to tab {index}: {target.url}"
        except Exception as e:
            return f"Error switching tab: {str(e)}"

    async def close_tab(self, index: int, agent_id: str) -> str:
        """Close a browser tab by index."""
        try:
            page = await _get_page(agent_id)
            pages = page.context.pages
            if index < 0 or index >= len(pages):
                return f"Error: Tab index {index} is out of range."
            await pages[index].close()
            return f"✓ Tab {index} closed. {len(page.context.pages) - 1} tab(s) remaining."
        except Exception as e:
            return f"Error closing tab: {str(e)}"

    async def list_tabs(self, agent_id: str) -> str:
        """List all open tabs in the agent's browser session."""
        try:
            page = await _get_page(agent_id)
            pages = page.context.pages
            lines = [f"  [{i}] {p.url}" for i, p in enumerate(pages)]
            return f"Open tabs ({len(pages)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing tabs: {str(e)}"

    # ------------------------------------------------------------------ #
    # Form Discovery & Iframe Handling
    # ------------------------------------------------------------------ #

    async def get_interactive_elements(self, agent_id: str, selector_scope: str = "") -> str:
        """Discover all interactive elements (inputs, selects, buttons, textareas)
        on the current page AND inside any iframes. Returns a structured list
        with CSS selectors the agent can use directly.

        This is the FIRST tool agents should call after navigating to a page
        with forms — never guess selectors."""
        try:
            page = await _get_page(agent_id)

            js_extract = """
            (scopeSelector) => {
                const root = scopeSelector
                    ? document.querySelector(scopeSelector)
                    : document.body;
                if (!root) return [];
                const interactables = root.querySelectorAll(
                    'input, textarea, select, button, [role="button"], [contenteditable="true"], a[href]'
                );
                return Array.from(interactables).slice(0, 60).map((el, i) => {
                    const tag = el.tagName.toLowerCase();
                    const type = el.getAttribute('type') || '';
                    const name = el.getAttribute('name') || '';
                    const id = el.getAttribute('id') || '';
                    const placeholder = el.getAttribute('placeholder') || '';
                    const ariaLabel = el.getAttribute('aria-label') || '';
                    const label = el.labels && el.labels[0] ? el.labels[0].textContent.trim() : '';
                    const value = (tag === 'select')
                        ? Array.from(el.options).map(o => o.text).slice(0, 5).join(', ')
                        : (el.value || '').slice(0, 50);
                    const text = (tag === 'button' || tag === 'a')
                        ? el.textContent.trim().slice(0, 60)
                        : '';
                    const visible = el.offsetParent !== null || el.offsetHeight > 0;
                    const required = el.hasAttribute('required');

                    // Build best CSS selector for this element
                    let selector = '';
                    if (id) selector = '#' + CSS.escape(id);
                    else if (name) selector = tag + '[name="' + name + '"]';
                    else if (ariaLabel) selector = tag + '[aria-label="' + ariaLabel + '"]';
                    else if (placeholder) selector = tag + '[placeholder="' + placeholder + '"]';
                    else selector = tag + ':nth-of-type(' + (i + 1) + ')';

                    return {
                        index: i,
                        tag, type, name, id, placeholder,
                        aria_label: ariaLabel,
                        label,
                        value,
                        text,
                        selector,
                        visible,
                        required,
                        frame: 'main'
                    };
                });
            }
            """

            # Extract from main page
            main_elements = await page.evaluate(js_extract, selector_scope)

            # Extract from iframes
            iframe_elements = []
            frames = page.frames
            for idx, frame in enumerate(frames):
                if frame == page.main_frame:
                    continue
                try:
                    frame_url = frame.url or "about:blank"
                    frame_els = await frame.evaluate(js_extract, "")
                    for el in frame_els:
                        el["frame"] = f"iframe[{idx}] ({frame_url[:60]})"
                        el["selector"] = f"iframe__{idx}__{el['selector']}"
                    iframe_elements.extend(frame_els)
                except Exception as fe:
                    iframe_elements.append({
                        "frame": f"iframe[{idx}]",
                        "error": str(fe)[:100]
                    })

            all_elements = main_elements + iframe_elements

            if not all_elements:
                return "No interactive elements found on this page (or inside iframes)."

            # Format as structured output
            lines = [f"Found {len(all_elements)} interactive element(s):\n"]
            for el in all_elements:
                if "error" in el:
                    lines.append(f"  ⚠️ {el['frame']}: Could not inspect — {el['error']}")
                    continue

                parts = []
                if el.get("label"):
                    parts.append(f"label=\"{el['label']}\"")
                if el.get("placeholder"):
                    parts.append(f"placeholder=\"{el['placeholder']}\"")
                if el.get("aria_label"):
                    parts.append(f"aria-label=\"{el['aria_label']}\"")
                if el.get("name"):
                    parts.append(f"name=\"{el['name']}\"")
                if el.get("id"):
                    parts.append(f"id=\"{el['id']}\"")
                if el.get("text"):
                    parts.append(f"text=\"{el['text']}\"")
                if el.get("value"):
                    parts.append(f"value=\"{el['value']}\"")
                if el.get("required"):
                    parts.append("REQUIRED")
                if not el.get("visible"):
                    parts.append("HIDDEN")

                tag_type = el['tag']
                if el.get('type'):
                    tag_type += f"[{el['type']}]"

                detail = ", ".join(parts)
                frame_tag = f" [{el['frame']}]" if el['frame'] != 'main' else ""

                lines.append(f"  [{el['index']}] <{tag_type}> selector=\"{el['selector']}\" {detail}{frame_tag}")

            return "\n".join(lines)
        except Exception as e:
            return f"Error getting interactive elements: {str(e)}"

    async def switch_to_frame(self, frame_index: int, agent_id: str) -> str:
        """Get info about a specific iframe by index.
        After calling this, use browser_eval_js with frame-aware selectors."""
        try:
            page = await _get_page(agent_id)
            frames = page.frames
            non_main = [f for f in frames if f != page.main_frame]
            if frame_index < 0 or frame_index >= len(non_main):
                return f"Error: Frame index {frame_index} out of range (0–{len(non_main)-1})."
            frame = non_main[frame_index]
            frame_url = frame.url or "about:blank"
            return f"✓ Frame {frame_index} info: URL={frame_url}, Name={frame.name or '(none)'}"
        except Exception as e:
            return f"Error switching to frame: {str(e)}"

    # ------------------------------------------------------------------ #
    # Internal Helpers
    # ------------------------------------------------------------------ #

    async def _try_in_frames(self, page, action: str, selector: str, text: str = "") -> bool:
        """Try to perform an action (click/fill/type) inside iframes when the main page fails."""
        frames = page.frames
        for frame in frames:
            if frame == page.main_frame:
                continue
            try:
                el = await frame.query_selector(selector)
                if el:
                    if action == "click":
                        await el.click(timeout=8_000)
                    elif action == "fill":
                        await frame.fill(selector, text, timeout=8_000)
                    elif action == "type":
                        await frame.type(selector, text, delay=30, timeout=8_000)
                    logger.info("✓ [BrowserTool] Found '%s' inside iframe (%s)", selector, frame.url[:60])
                    return True
            except Exception:
                continue
        return False

    # ------------------------------------------------------------------ #
    # Session Management
    # ------------------------------------------------------------------ #

    async def close_browser(self, agent_id: str) -> str:
        """Close and release the agent's browser session."""
        try:
            from core.tools.browser_pool import close_agent_browser
            closed = await close_agent_browser(agent_id)
            return "✓ Browser session closed for agent." if closed else "No browser session to close."
        except Exception as e:
            return f"Error closing browser: {str(e)}"


# Singleton
browser_tool = BrowserTool()
