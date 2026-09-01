"""
# backend/core/tools/browser_tool.py

Full-featured headless browser automation via Playwright.
Implements the Snapshot/Ref architecture for maximum
reliability and LLM token efficiency.

Core design:
  - browser_snapshot: Renders the live DOM as a compact Accessibility Tree.
    Every interactive element gets a numbered Ref (e.g. [12]).
    This is what the agent uses to UNDERSTAND and NAVIGATE the page.
  - browser_act: Unified action dispatcher. The agent clicks, types, hovers,
    selects, etc. by referring to Ref IDs from the snapshot.
  - browser_navigate: Navigate to a URL. Waits for page readiness, detects
    CAPTCHAs, and polls up to 45s for Browserbase to auto-resolve them.
  - Legacy tools (extract_text, extract_html, screenshot) are preserved for
    reading/scraping content after the agent has navigated to its destination.
  - Dialog handling: alerts, confirms, and prompts are caught automatically
    and surfaced to the agent instead of hanging the browser.

All screenshots are automatically streamed to the team EventBus so humans
can watch agents browse in real-time from the frontend.
"""

import asyncio
import base64
import json
import logging
import os
import re
from typing import Optional

from core.chat.event_bus import event_bus

logger = logging.getLogger("carole.browser")

MAX_TEXT_CHARS = 100_000
MAX_HTML_CHARS = 100_000

_SNAPSHOT_JS_PATH = os.path.join(os.path.dirname(__file__), "build_dom_tree.js")
try:
    with open(_SNAPSHOT_JS_PATH, "r", encoding="utf-8") as _f:
        _SNAPSHOT_JS = _f.read().rstrip(";\n\r ")
except Exception as e:
    logger.error(f"Failed to load build_dom_tree.js: {e}")
    _SNAPSHOT_JS = "() => { return { map: {}, rootId: null }; }"

# -- CAPTCHA detection patterns ------------------------------------------------
CAPTCHA_TITLE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"just a moment",           # Cloudflare
        r"attention required",      # Cloudflare
        r"ddos.?protection",        # Generic
        r"access denied",
        r"verify you are human",
        r"unusual traffic",         # Google
        r"please enable cookies",
        r"checking your browser",
    ]
]

CAPTCHA_URL_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"google\.com/sorry",
        r"challenges\.cloudflare\.com",
        r"captcha",
        r"human-verification",
    ]
]


def _is_captcha_page(url: str, title: str) -> bool:
    """Returns True if the current page looks like a CAPTCHA/bot-challenge wall."""
    for p in CAPTCHA_URL_PATTERNS:
        if p.search(url):
            return True
    for p in CAPTCHA_TITLE_PATTERNS:
        if p.search(title):
            return True
    return False


async def _get_page(agent_id: str):
    from core.tools.browser_pool import get_page
    return await get_page(agent_id)


async def _publish_screenshot(page, agent_id: str, agent_name: str, team_id: str, label: str = ""):
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


async def _wait_for_page_readiness(
    page,
    agent_id: str,
    agent_name: str,
    team_id: str,
    captcha_timeout: float = 120.0,
) -> str:
    """
    Smart page readiness helper. Called after any navigation or major action.

    1. Waits for networkidle / domcontentloaded so JS-heavy SPAs fully render.
    2. Detects CAPTCHA / bot-challenge walls.
    3. If a CAPTCHA is found, polls up to `captcha_timeout` seconds to let
       Browserbase (or another provider) auto-resolve it in the background.
    4. Returns a status string: "ready", "captcha_resolved", or "captcha_timeout".
    """
    # Step 1: Wait for page to settle (best-effort)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:
        pass
    try:
        await page.wait_for_load_state("networkidle", timeout=12_000)
    except Exception:
        pass

    # Step 2: Check for CAPTCHA
    title = await page.title()
    url = page.url
    if not _is_captcha_page(url, title):
        return "ready"

    logger.info(
        "🔒 [BrowserTool] CAPTCHA detected on '%s'. "
        "Polling up to %.0fs for auto-resolution...",
        url, captcha_timeout,
    )
    await _publish_screenshot(page, agent_id, agent_name, team_id, "⏳ CAPTCHA detected — waiting for auto-resolve...")

    # Step 3: Poll until CAPTCHA resolves or timeout
    poll_interval = 3.0
    elapsed = 0.0
    while elapsed < captcha_timeout:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        try:
            await page.wait_for_load_state("networkidle", timeout=6_000)
        except Exception:
            pass
        title = await page.title()
        url = page.url
        if not _is_captcha_page(url, title):
            logger.info("✅ [BrowserTool] CAPTCHA resolved after %.0fs.", elapsed)
            await _publish_screenshot(
                page, agent_id, agent_name, team_id, "✅ CAPTCHA resolved!"
            )
            return "captcha_resolved"

    logger.warning("⚠️ [BrowserTool] CAPTCHA still present after %.0fs timeout.", captcha_timeout)
    return "captcha_timeout"


class BrowserTool:
    """
    Provides a complete, browser automation suite.

    Primary workflow:
        1. navigate(url)           → go to a page, auto-waits, CAPTCHA-polls
        2. snapshot()              → get the Accessibility Tree with numbered Refs
        3. act(kind, ref, ...)     → click/type/hover by Ref number from snapshot
        4. snapshot()              → re-check state after action

    Secondary workflow (scraping / reading content):
        - extract_text(selector)   → read raw text from a section of the page
        - extract_html(selector)   → read raw HTML (for structured data)
        - screenshot()             → capture a screenshot
    """

    def __init__(self):
        # Per-agent dialog queue: agent_id → list of dialog info dicts
        self._dialog_queues: dict = {}
        self._last_selector_maps: dict = {}

    # -- Dialog handling setup --------------------------------------------------
    def _resolve_selector(self, selector: str, page) -> str:
        # If the selector is just digits (or surrounded by brackets like [5]), resolve it
        clean_sel = selector.strip("[] ")
        if clean_sel.isdigit():
            refs = self._last_selector_maps.get(page.context, {})
            if clean_sel in refs:
                xpath = refs[clean_sel]["selector"]
                if not xpath.startswith("xpath="):
                    xpath = "xpath=" + xpath
                return xpath
        return selector


    def _setup_dialog_handler(self, page, agent_id: str):
        """Attach a dialog listener to a page. Dialogs are queued for the agent."""
        async def _on_dialog(dialog):
            info = {
                "type": dialog.type,
                "message": dialog.message[:500],
                "default_value": dialog.default_value,
                "dialog_obj": dialog,
            }
            if agent_id not in self._dialog_queues:
                self._dialog_queues[agent_id] = []
            self._dialog_queues[agent_id].append(info)
            logger.info(
                "🔔 [BrowserTool] Dialog for agent %s: type=%s msg=%s",
                agent_id[:8], dialog.type, dialog.message[:80],
            )
            # Auto-dismiss non-confirm dialogs to prevent hanging
            if dialog.type in ("alert", "beforeunload"):
                try:
                    await dialog.accept()
                    info["auto_dismissed"] = True
                except Exception:
                    pass

        page.on("dialog", _on_dialog)

    # -- Navigation ------------------------------------------------------------

    async def navigate(self, url: str, agent_id: str, agent_name: str, team_id: str,
                       wait_until: str = "domcontentloaded") -> str:
        """Navigate to a URL. Returns the page title + a compact snapshot.
        Automatically waits for JS rendering, detects CAPTCHAs, and polls
        up to 45 seconds for providers like Browserbase to solve them."""
        try:
            page = await _get_page(agent_id)
            self._setup_dialog_handler(page, agent_id)

            response = await page.goto(url, wait_until=wait_until, timeout=30_000)
            status = response.status if response else "unknown"

            readiness = await _wait_for_page_readiness(page, agent_id, agent_name, team_id)
            await _publish_screenshot(page, agent_id, agent_name, team_id, f"Navigated to {url}")

            title = await page.title()
            captcha_note = ""
            if readiness == "captcha_resolved":
                captcha_note = "\n⚠️ Note: A CAPTCHA was detected and auto-resolved by the browser provider."
            elif readiness == "captcha_timeout":
                captcha_note = (
                    "\n⚠️ Warning: A CAPTCHA wall was detected and could NOT be automatically resolved. "
                    "The page content below may be the CAPTCHA page, not the destination."
                )

            # Check for intercepted download
            if getattr(page, "_last_download_path", None):
                import json
                dl_path = page._last_download_path
                dl_url = getattr(page, "_last_download_url", url)
                page._last_download_path = None
                return json.dumps({
                    "_is_file": True,
                    "local_path": dl_path,
                    "mime_type": "application/octet-stream",
                    "source_url": dl_url
                })

            # Return a compact snapshot instead of full HTML
            snapshot_text = await self._build_snapshot_text(page)
            iframe_count = await page.evaluate("document.querySelectorAll('iframe').length")
            iframe_hint = ""
            if iframe_count > 0:
                iframe_hint = (
                    f"\n⚠️ Page has {iframe_count} iframe(s). Elements inside iframes "
                    f"may need browser_act with frame_index parameter."
                )

            return (
                f"✓ Navigated to {url}\n"
                f"  Status: {status} | Title: {title}{captcha_note}{iframe_hint}\n\n"
                f"-- Page Snapshot --\n{snapshot_text}"
            )
        except Exception as e:
            return f"Error navigating to '{url}': {str(e)}"

    # -- Snapshot --------------------------------------------------------------

    async def _build_snapshot_text(self, page) -> str:
        try:
            arg = {"doHighlightElements": True, "focusHighlightIndex": -1, "viewportExpansion": 0, "debugMode": False}
            result = await page.evaluate(_SNAPSHOT_JS, arg)
            
            dom_map = result.get("map", {})
            root_id = result.get("rootId")
            
            if not dom_map or root_id is None:
                return "Error: Could not extract DOM tree."

            # Save the refs for act() using xpath
            refs = {}
            for index, node in dom_map.items():
                if node.get("highlightIndex") is not None:
                    # Map the highlight index to the xpath so act() can click it
                    refs[str(node["highlightIndex"])] = {"selector": node.get("xpath")}
            
            self._last_selector_maps[page.context] = refs
            
            # Build the text tree
            text_lines = []
            
            def build_tree(node_id, depth):
                if str(node_id) not in dom_map:
                    return
                node = dom_map[str(node_id)]
                
                if node.get("type") == "TEXT_NODE":
                    if node.get("isVisible"):
                        text = node.get("text", "").strip()
                        if text:
                            text_lines.append(f"{'  '*depth}{text}")
                    return
                    
                idx = node.get("highlightIndex")
                if idx is not None:
                    tag = node.get("tagName", "").lower()
                    attrs = []
                    for k, v in node.get("attributes", {}).items():
                        if k in ["name", "type", "value", "placeholder", "aria-label", "checked", "href"]:
                            attrs.append(f"{k}='{v}'")
                    attr_str = " " + " ".join(attrs) if attrs else ""
                    
                    text = ""
                    for child_id in node.get("children", []):
                        child = dom_map.get(str(child_id))
                        if child and child.get("type") == "TEXT_NODE":
                            text += " " + child.get("text", "").strip()
                            
                    text_lines.append(f"{'  '*depth}[{idx}] <{tag}{attr_str}> {text.strip()}")
                    
                for child_id in node.get("children", []):
                    build_tree(child_id, depth + 1 if idx is not None else depth)
                    
            build_tree(root_id, 0)
            return "\\n".join(text_lines)
            
        except Exception as e:
            return f"Error extracting page text: {str(e)}"

    # -- Unified Act ----------------------------------------------------------─

    async def act(self, kind: str, agent_id: str, agent_name: str, team_id: str,
                  ref: Optional[int] = None,
                  selector: Optional[str] = None,
                  text: Optional[str] = None,
                  key: Optional[str] = None,
                  value: Optional[str] = None,
                  x: Optional[float] = None,
                  y: Optional[float] = None,
                  frame_index: Optional[int] = None,
                  slow_type: bool = False) -> str:
        """
        Unified browser action dispatcher. Interact with page elements by Ref number
        (from browser_snapshot) or by CSS selector.

        kind options:
          - click       : click a button/link. Params: ref OR selector.
          - type        : type text into an input. Params: ref OR selector, text.
          - clear       : clear an input field. Params: ref OR selector.
          - hover       : hover over an element. Params: ref OR selector.
          - select      : pick a <select> option. Params: ref OR selector, value.
          - check       : check a checkbox. Params: ref OR selector.
          - uncheck     : uncheck a checkbox. Params: ref OR selector.
          - press       : press a keyboard key. Params: key (e.g. 'Enter','Tab','Escape').
          - scroll_down : scroll the page down. No extra params needed.
          - scroll_up   : scroll the page up. No extra params needed.
          - coords      : click at exact screen coordinates. Params: x, y.

        ref: The numbered Ref from a snapshot (e.g. 12).
        selector: A CSS selector fallback if no ref is available.
        frame_index: Target an iframe by index (0-based, excluding main frame).
        """
        try:
            page = await _get_page(agent_id)

            # Resolve the target element's CSS selector from a ref
            css_selector = None
            if ref is not None:
                try:
                    result = await page.evaluate(_SNAPSHOT_JS)
                    refs = result.get("refs", {})
                    ref_data = refs.get(str(ref)) or refs.get(ref)
                    if ref_data and ref_data.get("selector"):
                        css_selector = ref_data["selector"]
                    else:
                        # Ref not found — take a fresh snapshot and report
                        return (
                            f"⚠️ Ref [{ref}] not found in current page snapshot "
                            f"(page may have changed). "
                            f"Call browser_snapshot again to get fresh refs."
                        )
                except Exception as e:
                    logger.warning("Failed to resolve ref %s: %s", ref, e)
                    return f"Error resolving ref [{ref}]: {e}"
            elif selector:
                css_selector = selector
            elif kind not in ("press", "scroll_down", "scroll_up", "coords"):
                return f"Error: '{kind}' requires a ref or selector."

            # Determine frame context
            frame = page
            if frame_index is not None:
                non_main = [f for f in page.frames if f != page.main_frame]
                if 0 <= frame_index < len(non_main):
                    frame = non_main[frame_index]
                else:
                    return f"Error: frame_index {frame_index} out of range (0–{len(non_main)-1})."

            # -- Execute the action --------------------------------------------
            if kind == "click":
                try:
                    await frame.click(css_selector, timeout=10_000)
                except Exception:
                    # Try inside iframes if not already in a frame
                    if frame == page:
                        clicked = await self._try_in_frames(page, "click", css_selector)
                        if not clicked:
                            raise

            elif kind == "type":
                if not text:
                    return "Error: 'type' requires text parameter."
                try:
                    if slow_type:
                        await frame.click(css_selector, timeout=8_000)
                        await frame.type(css_selector, text, delay=40, timeout=15_000)
                    else:
                        await frame.fill(css_selector, text, timeout=10_000)
                except Exception:
                    if frame == page:
                        filled = await self._try_in_frames(page, "fill", css_selector, text)
                        if not filled:
                            raise

            elif kind == "clear":
                try:
                    await frame.fill(css_selector, "", timeout=8_000)
                except Exception:
                    await frame.evaluate(
                        f"document.querySelector('{css_selector}').value = ''"
                    )

            elif kind == "hover":
                await frame.hover(css_selector, timeout=10_000)

            elif kind == "select":
                if not value:
                    return "Error: 'select' requires value parameter."
                try:
                    await frame.select_option(css_selector, value=value, timeout=8_000)
                except Exception:
                    await frame.select_option(css_selector, label=value, timeout=8_000)

            elif kind == "check":
                await frame.check(css_selector, timeout=8_000)

            elif kind == "uncheck":
                await frame.uncheck(css_selector, timeout=8_000)

            elif kind == "press":
                if not key:
                    return "Error: 'press' requires key parameter."
                await page.keyboard.press(key)

            elif kind == "scroll_down":
                await page.evaluate("window.scrollBy(0, 600)")

            elif kind == "scroll_up":
                await page.evaluate("window.scrollBy(0, -600)")

            elif kind == "coords":
                if x is None or y is None:
                    return "Error: 'coords' requires x and y parameters."
                await page.mouse.click(x, y)

            else:
                return f"Error: Unknown kind '{kind}'. Valid: click, type, clear, hover, select, check, uncheck, press, scroll_down, scroll_up, coords."

            # -- Post-action: wait for page to settle --------------------------
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5_000)
            except Exception:
                pass
            try:
                await page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                pass

            # Check for intercepted download
            if getattr(page, "_last_download_path", None):
                import json
                dl_path = page._last_download_path
                dl_url = getattr(page, "_last_download_url", page.url)
                page._last_download_path = None
                return json.dumps({
                    "_is_file": True,
                    "local_path": dl_path,
                    "mime_type": "application/octet-stream",
                    "source_url": dl_url
                })

            await _publish_screenshot(page, agent_id, agent_name, team_id, f"act:{kind}")

            ref_label = f"[{ref}]" if ref else (selector or "")
            return (
                f"✓ {kind} on {ref_label} succeeded. Page: {page.url}\n"
                f"Call browser_snapshot to see the updated page state."
            )

        except Exception as e:
            return f"Error performing act '{kind}': {str(e)}"

    # -- Dialog handling ------------------------------------------------------─

    async def handle_dialog(self, agent_id: str, accept: bool = True,
                            prompt_text: str = "") -> str:
        """
        Accept or dismiss a pending browser dialog (alert, confirm, prompt).
        Use browser_snapshot first to see if there is a pending dialog.

        accept: True to click OK/Accept, False to click Cancel/Dismiss.
        prompt_text: For 'prompt' dialogs, the text to enter before accepting.
        """
        pending = self._dialog_queues.get(agent_id, [])
        if not pending:
            return "No pending dialogs for this agent."
        info = pending.pop(0)
        dialog = info.get("dialog_obj")
        if dialog is None:
            return "Dialog already handled."
        try:
            if accept:
                await dialog.accept(prompt_text or "")
                return f"✓ Dialog accepted. (type={info['type']}, message={info['message'][:80]!r})"
            else:
                await dialog.dismiss()
                return f"✓ Dialog dismissed. (type={info['type']}, message={info['message'][:80]!r})"
        except Exception as e:
            return f"Error handling dialog: {e}"

    # -- Navigation helpers ----------------------------------------------------

    async def go_back(self, agent_id: str, agent_name: str, team_id: str) -> str:
        try:
            page = await _get_page(agent_id)
            await page.go_back(timeout=10_000)
            await _wait_for_page_readiness(page, agent_id, agent_name, team_id)
            await _publish_screenshot(page, agent_id, agent_name, team_id, "Go back")
            return f"✓ Went back. Now at: {page.url}"
        except Exception as e:
            return f"Error going back: {str(e)}"

    async def go_forward(self, agent_id: str, agent_name: str, team_id: str) -> str:
        try:
            page = await _get_page(agent_id)
            await page.go_forward(timeout=10_000)
            await _wait_for_page_readiness(page, agent_id, agent_name, team_id)
            await _publish_screenshot(page, agent_id, agent_name, team_id, "Go forward")
            return f"✓ Went forward. Now at: {page.url}"
        except Exception as e:
            return f"Error going forward: {str(e)}"

    async def reload(self, agent_id: str, agent_name: str, team_id: str) -> str:
        try:
            page = await _get_page(agent_id)
            await page.reload(wait_until="domcontentloaded", timeout=15_000)
            await _wait_for_page_readiness(page, agent_id, agent_name, team_id)
            await _publish_screenshot(page, agent_id, agent_name, team_id, "Page reloaded")
            return f"✓ Page reloaded: {page.url}"
        except Exception as e:
            return f"Error reloading: {str(e)}"

    async def get_current_url(self, agent_id: str) -> str:
        try:
            page = await _get_page(agent_id)
            return f"Current URL: {page.url}"
        except Exception as e:
            return f"Error getting URL: {str(e)}"

    # -- Screenshots ----------------------------------------------------------─

    async def screenshot(self, agent_id: str, agent_name: str, team_id: str,
                         full_page: bool = False) -> str:
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

    # -- Content Extraction (for scraping/reading) ----------------------------─

    async def extract_text(self, selector: str, agent_id: str) -> str:
        """Extract visible text from a specific element or the whole page body.
        Use this to read content after navigating — NOT for finding interactive elements."""
        try:
            page = await _get_page(agent_id)
            selector = self._resolve_selector(selector, page)
            target = selector if selector else "body"
            text = await page.inner_text(target, timeout=8_000)
            text = text[:MAX_TEXT_CHARS]
            return text if text else "No text found."
        except Exception as e:
            return f"Error extracting text from '{selector}': {str(e)}"

    async def extract_html(self, selector: str, agent_id: str) -> str:
        """Extract the raw HTML of an element. Use for structured data / parsing."""
        try:
            page = await _get_page(agent_id)
            selector = self._resolve_selector(selector, page)
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
        try:
            page = await _get_page(agent_id)
            selector = self._resolve_selector(selector, page)
            selector = self._resolve_selector(selector, page)
            element = await page.query_selector(selector)
            if not element:
                return f"Error: Element '{selector}' not found."
            value = await element.get_attribute(attribute)
            return f"Attribute '{attribute}' of '{selector}': {value}"
        except Exception as e:
            return f"Error getting attribute: {str(e)}"

    async def evaluate_js(self, script: str, agent_id: str) -> str:
        try:
            page = await _get_page(agent_id)
            result = await page.evaluate(script)
            result_str = json.dumps(result, default=str) if not isinstance(result, str) else result
            return result_str[:3000]
        except Exception as e:
            return f"Error running JS: {str(e)}"

    async def get_all_links(self, agent_id: str, limit: int = 30) -> str:
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

    async def get_page_metadata(self, agent_id: str) -> str:
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

    # -- Waiting --------------------------------------------------------------─

    async def wait_for_selector(self, selector: str, agent_id: str, timeout_ms: int = 10000) -> str:
        try:
            page = await _get_page(agent_id)
            await page.wait_for_selector(selector, timeout=timeout_ms)
            return f"✓ Element '{selector}' appeared in DOM."
        except Exception as e:
            return f"Timeout/error waiting for '{selector}': {str(e)}"

    async def wait_for_navigation(self, agent_id: str, timeout_ms: int = 10000) -> str:
        try:
            page = await _get_page(agent_id)
            await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            return f"✓ Navigation complete. Now at: {page.url}"
        except Exception as e:
            return f"Timeout/error waiting for navigation: {str(e)}"

    async def wait_ms(self, ms: int, agent_id: str) -> str:
        ms = min(ms, 30_000)
        await asyncio.sleep(ms / 1000)
        return f"✓ Waited {ms}ms."

    # -- Cookies & Storage ----------------------------------------------------─

    async def get_cookies(self, agent_id: str) -> str:
        try:
            page = await _get_page(agent_id)
            cookies = await page.context.cookies()
            if not cookies:
                return "No cookies set."
            lines = [
                f"  {c['name']}={c['value'][:40]} (domain={c.get('domain', '')})"
                for c in cookies[:30]
            ]
            return f"Cookies ({len(cookies)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error getting cookies: {str(e)}"

    async def clear_cookies(self, agent_id: str) -> str:
        try:
            page = await _get_page(agent_id)
            await page.context.clear_cookies()
            return "✓ All cookies cleared."
        except Exception as e:
            return f"Error clearing cookies: {str(e)}"

    # -- Tab Management --------------------------------------------------------

    async def open_new_tab(self, url: str, agent_id: str, agent_name: str, team_id: str) -> str:
        try:
            from core.tools.browser_pool import get_new_page
            new_page = await get_new_page(agent_id)
            self._setup_dialog_handler(new_page, agent_id)
            await new_page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await _wait_for_page_readiness(new_page, agent_id, agent_name, team_id)
            await _publish_screenshot(new_page, agent_id, agent_name, team_id, f"New tab: {url}")
            page = await _get_page(agent_id)
            return f"✓ Opened new tab at {url} (tab index {len(page.context.pages) - 1})"
        except Exception as e:
            return f"Error opening new tab: {str(e)}"

    async def switch_tab(self, index: int, agent_id: str, agent_name: str, team_id: str) -> str:
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
        try:
            page = await _get_page(agent_id)
            pages = page.context.pages
            lines = [f"  [{i}] {p.url}" for i, p in enumerate(pages)]
            return f"Open tabs ({len(pages)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing tabs: {str(e)}"

    # -- Session Management ----------------------------------------------------

    async def close_browser(self, agent_id: str) -> str:
        try:
            from core.tools.browser_pool import close_agent_browser
            closed = await close_agent_browser(agent_id)
            self._dialog_queues.pop(agent_id, None)
            return "✓ Browser session closed for agent." if closed else "No browser session to close."
        except Exception as e:
            return f"Error closing browser: {str(e)}"

    # -- Legacy compatibility: get_interactive_elements ------------------------
    # Kept for backward compatibility in case any older tool registrations still
    # call this. It now delegates to snapshot().

    async def get_interactive_elements(self, agent_id: str, selector_scope: str = "") -> str:
        """Deprecated: use browser_snapshot instead. Returns a snapshot."""
        page = await _get_page(agent_id)
        return await self._build_snapshot_text(page)

    # -- Internal helpers ------------------------------------------------------

    async def _try_in_frames(self, page, action: str, selector: str, text: str = "") -> bool:
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

    # -- Screenshot element ----------------------------------------------------

    async def screenshot_element(self, selector: str, agent_id: str, agent_name: str, team_id: str) -> str:
        try:
            page = await _get_page(agent_id)
            selector = self._resolve_selector(selector, page)
            selector = self._resolve_selector(selector, page)
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

    async def find_elements(self, selector: str, agent_id: str, limit: int = 20) -> str:
        try:
            page = await _get_page(agent_id)
            selector = self._resolve_selector(selector, page)
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

    async def scroll_to_element(self, selector: str, agent_id: str) -> str:
        try:
            page = await _get_page(agent_id)
            selector = self._resolve_selector(selector, page)
            element = await page.query_selector(selector)
            if not element:
                return f"Error: Element '{selector}' not found."
            await element.scroll_into_view_if_needed()
            return f"✓ Scrolled to element: {selector}"
        except Exception as e:
            return f"Error scrolling to element: {str(e)}"

    async def switch_to_frame(self, frame_index: int, agent_id: str) -> str:
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

    # -- Legacy scroll / click methods ----------------------------------------─

    async def scroll(self, direction: str, amount: int, agent_id: str, selector: str = "") -> str:
        try:
            page = await _get_page(agent_id)
            dx = dy = 0
            if direction == "down":   dy = amount
            elif direction == "up":   dy = -amount
            elif direction == "right": dx = amount
            elif direction == "left":  dx = -amount
            else:
                return f"Error: Unknown direction '{direction}'. Use: up/down/left/right."
            if selector:
                await page.evaluate(f"document.querySelector('{selector}')?.scrollBy({dx}, {dy})")
            else:
                await page.evaluate(f"window.scrollBy({dx}, {dy})")
            return f"✓ Scrolled {direction} by {amount}px"
        except Exception as e:
            return f"Error scrolling: {str(e)}"

    async def click(self, selector: str, agent_id: str, agent_name: str = "", team_id: str = "") -> str:
        """Legacy click by CSS selector. Prefer browser_act(kind='click', ref=N)."""
        try:
            page = await _get_page(agent_id)
            selector = self._resolve_selector(selector, page)
            try:
                await page.click(selector, timeout=10_000)
            except Exception:
                clicked = await self._try_in_frames(page, "click", selector)
                if not clicked:
                    raise
            try:
                await page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                pass
            if team_id:
                await _publish_screenshot(page, agent_id, agent_name, team_id, f"Clicked: {selector}")
            return f"✓ Clicked element: {selector}"
        except Exception as e:
            return f"Error clicking '{selector}': {str(e)}"

    async def click_text(self, text: str, agent_id: str, agent_name: str = "", team_id: str = "") -> str:
        """Legacy click by visible text. Prefer browser_act(kind='click', ref=N)."""
        try:
            page = await _get_page(agent_id)
            await page.get_by_text(text, exact=False).first.click(timeout=10_000)
            try:
                await page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                pass
            if team_id:
                await _publish_screenshot(page, agent_id, agent_name, team_id, f"Clicked text: {text}")
            return f"✓ Clicked element with text: '{text}'"
        except Exception as e:
            return f"Error clicking text '{text}': {str(e)}"

    async def type_text(self, selector: str, text: str, agent_id: str, clear_first: bool = True) -> str:
        """Legacy type by CSS selector. Prefer browser_act(kind='type', ref=N, text='...')."""
        try:
            page = await _get_page(agent_id)
            selector = self._resolve_selector(selector, page)
            try:
                if clear_first:
                    await page.fill(selector, text, timeout=10_000)
                else:
                    await page.type(selector, text, delay=30, timeout=10_000)
            except Exception:
                filled = await self._try_in_frames(
                    page, "fill" if clear_first else "type", selector, text
                )
                if not filled:
                    raise
            return f"✓ Typed '{text[:80]}{'...' if len(text) > 80 else ''}' into {selector}"
        except Exception as e:
            return f"Error typing into '{selector}': {str(e)}"

    async def press_key(self, key: str, agent_id: str) -> str:
        """Press a keyboard key. Prefer browser_act(kind='press', key='Enter')."""
        try:
            page = await _get_page(agent_id)
            await page.keyboard.press(key)
            try:
                await page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                pass
            return f"✓ Pressed key: {key}"
        except Exception as e:
            return f"Error pressing key '{key}': {str(e)}"

    async def hover(self, selector: str, agent_id: str, agent_name: str = "", team_id: str = "") -> str:
        try:
            page = await _get_page(agent_id)
            selector = self._resolve_selector(selector, page)
            await page.hover(selector, timeout=10_000)
            if team_id:
                await _publish_screenshot(page, agent_id, agent_name, team_id, f"Hover: {selector}")
            return f"✓ Hovered over: {selector}"
        except Exception as e:
            return f"Error hovering over '{selector}': {str(e)}"

    async def select_option(self, selector: str, value: str, agent_id: str) -> str:
        try:
            page = await _get_page(agent_id)
            selector = self._resolve_selector(selector, page)
            try:
                selected = await page.select_option(selector, value=value, timeout=8_000)
            except Exception:
                selected = await page.select_option(selector, label=value, timeout=8_000)
            return f"✓ Selected '{value}' in {selector} (selected: {selected})"
        except Exception as e:
            return f"Error selecting option in '{selector}': {str(e)}"

    async def check_checkbox(self, selector: str, checked: bool, agent_id: str) -> str:
        try:
            page = await _get_page(agent_id)
            selector = self._resolve_selector(selector, page)
            if checked:
                await page.check(selector, timeout=8_000)
            else:
                await page.uncheck(selector, timeout=8_000)
            state = "checked" if checked else "unchecked"
            return f"✓ Checkbox '{selector}' {state}"
        except Exception as e:
            return f"Error on checkbox '{selector}': {str(e)}"


# Singleton
browser_tool = BrowserTool()
