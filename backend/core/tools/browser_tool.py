"""
Browser tools using page-local, frame-aware DOM-node refs.

Refs are valid only for the last snapshot on the active page.
A detached node, replaced document, changed active tab, or newer snapshot
invalidates the old reference instead of silently retargeting it.
"""

import asyncio
import base64
import functools
import inspect
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from core.chat.event_bus import event_bus

logger = logging.getLogger("carole.browser")

MAX_TEXT_CHARS = 100_000
MAX_HTML_CHARS = 100_000
MAX_SNAPSHOT_CHARS = 14_000
MAX_FRAMES = 12

_SNAPSHOT_JS = Path(__file__).with_name("build_dom_tree.js").read_text(
    encoding="utf-8"
)

_CAPTCHA_RE = re.compile(
    r"just a moment|attention required|verify you are human|"
    r"unusual traffic|checking your browser|human.verification|"
    r"google\.com/sorry|challenges\.cloudflare\.com",
    re.IGNORECASE,
)


def _is_captcha_page(url: str, title: str) -> bool:
    return bool(_CAPTCHA_RE.search(f"{url}\n{title}"))


def _safe_url(url: str) -> str:
    from core.llm.config_manager import load_config
    from core.tools.ssrf_guard import assert_safe_public_url

    cfg = (load_config() or {}).get("browser_automation") or {}
    return assert_safe_public_url(
        url, allow_local=cfg.get("allow_local_urls") is True
    )


async def _get_page(agent_id: str):
    from core.tools.browser_pool import get_page
    return await get_page(agent_id)


async def _publish_screenshot(
    page,
    agent_id: str,
    agent_name: str,
    team_id: str,
    label: str = "",
):
    if not team_id:
        return

    try:
        # Mask common credential/payment fields. Screenshots may still contain
        # other PII; enforce access control and retention at the EventBus/UI.
        mask = page.locator(
            "input[type=password],"
            "input[autocomplete=one-time-code],"
            "input[autocomplete=cc-number],"
            "input[autocomplete=cc-csc]"
        )
        shot = await page.screenshot(
            type="jpeg",
            quality=60,
            full_page=False,
            mask=[mask],
            timeout=5_000,
        )
        await asyncio.wait_for(
            event_bus.publish(
                f"team:{team_id}",
                {
                    "type": "browser_screenshot",
                    "sender_id": agent_id,
                    "sender_name": agent_name,
                    "url": page.url,
                    "label": label,
                    "image_base64": (
                        "data:image/jpeg;base64,"
                        + base64.b64encode(shot).decode("ascii")
                    ),
                },
            ),
            timeout=3,
        )
    except Exception:
        # Screenshot delivery must not make an otherwise successful action fail.
        logger.debug("Screenshot delivery failed", exc_info=True)


async def _wait_for_page_readiness(
    page,
    agent_id: str,
    agent_name: str,
    team_id: str,
    captcha_timeout: float = 15.0,
) -> str:
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=10_000)
    except Exception:
        pass

    # networkidle is not a readiness guarantee for SPAs and can add seconds
    # to every action. Let subsequent snapshots observe asynchronous changes.
    deadline = time.monotonic() + max(0, captcha_timeout)

    while True:
        title = await asyncio.wait_for(page.title(), timeout=5)
        if not _is_captcha_page(page.url, title):
            return "ready"

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "captcha_timeout"

        await asyncio.sleep(min(1.0, remaining))


def _session_method(fn):
    """Serialize public tool calls and install nonblocking page handlers."""
    signature = inspect.signature(fn)

    @functools.wraps(fn)
    async def wrapper(self, *args, **kwargs):
        bound = signature.bind(self, *args, **kwargs)
        bound.apply_defaults()
        agent_id = bound.arguments["agent_id"]

        from core.tools.browser_pool import browser_session

        try:
            async with browser_session(agent_id) as page:
                self._setup_dialog_handler(page, agent_id)
                return await fn(self, *args, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Do not return arbitrary exception strings containing passwords,
            # proxy URLs, request headers, or typed input.
            logger.warning(
                "Browser operation failed: operation=%s error=%s msg=%s",
                fn.__name__,
                type(exc).__name__,
                exc,
            )
            return (
                f"Error: {fn.__name__} failed ({type(exc).__name__}). "
                "Refresh the snapshot before retrying."
            )

    return wrapper


class BrowserTool:
    def _setup_dialog_handler(self, page, agent_id: str):
        if getattr(page, "_carole_dialog_attached", False):
            return

        page._carole_dialog_attached = True
        page._carole_dialog_events = []
        page._carole_next_dialog = None

        async def on_dialog(dialog):
            policy = page._carole_next_dialog
            page._carole_next_dialog = None

            if policy and time.monotonic() <= policy["expires"]:
                accept = policy["accept"]
                prompt_text = policy["prompt_text"]
            else:
                accept = dialog.type == "alert"
                prompt_text = ""

            event = {
                "type": dialog.type,
                "message": dialog.message[:300],
                "accepted": accept,
            }

            try:
                if accept:
                    if dialog.type == "prompt":
                        await dialog.accept(prompt_text)
                    else:
                        await dialog.accept()
                else:
                    await dialog.dismiss()
            except Exception:
                event["resolution_failed"] = True

            page._carole_dialog_events.append(event)
            del page._carole_dialog_events[:-10]

        res = page.on("dialog", on_dialog)
        if inspect.isawaitable(res):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(res)
            except RuntimeError:
                pass

    def _invalidate_refs(self, page):
        page._carole_refs = {}
        page._carole_snapshot_id = None

    async def _build_snapshot_text(self, page) -> str:
        self._invalidate_refs(page)
        snapshot_id = uuid.uuid4().hex
        refs = {}
        lines = []
        used = 0
        stopped = False

        def append(line: str) -> bool:
            nonlocal used
            if used + len(line) + 1 > MAX_SNAPSHOT_CHARS:
                return False
            lines.append(line)
            used += len(line) + 1
            return True

        frames = list(page.frames)
        for frame_index, frame in enumerate(frames[:MAX_FRAMES]):
            try:
                result = await asyncio.wait_for(
                    frame.evaluate(
                        _SNAPSHOT_JS,
                        {
                            "maxNodes": 5000,
                            "maxItems": 300,
                            "viewportExpansion": 300,
                        },
                    ),
                    timeout=8,
                )
            except Exception:
                append(f"FRAME {frame_index}: snapshot unavailable")
                continue

            if not append(
                f"FRAME {frame_index} "
                f"URL={json.dumps(frame.url)} "
                f"SCROLL={json.dumps(result.get('scroll', {}))}"
            ):
                break

            for item in result.get("items", []):
                if item.get("kind") == "text":
                    line = item.get("text", "")
                else:
                    ref = str(len(refs))
                    line = (
                        f"[{ref}] <{item.get('tag', '?')}> "
                        + json.dumps(
                            item.get("attrs", {}),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )

                if not append(line):
                    stopped = True
                    break

                if item.get("kind") == "element":
                    refs[ref] = {
                        "frame": frame,
                        "token": result["token"],
                        "local_ref": item["ref"],
                    }

            if result.get("truncated"):
                append("[Frame snapshot truncated; scroll or narrow the task.]")
            if stopped:
                break

        if len(frames) > MAX_FRAMES or stopped:
            lines.append("[Snapshot truncated.]")

        events = getattr(page, "_carole_dialog_events", [])
        if events:
            lines.append("RECENT DIALOGS: " + json.dumps(events[-3:]))

        page._carole_refs = refs
        page._carole_snapshot_id = snapshot_id

        return "\n".join(lines) or "(No visible page content.)"

    async def _target(
        self,
        page,
        ref=None,
        selector=None,
        frame_index=None,
        snapshot_id=None,
    ):
        """
        Return (Locator or ElementHandle, dispose_after_use).

        Ref resolution never rebuilds a snapshot and never searches other frames.
        """
        if snapshot_id is not None:
            if snapshot_id != getattr(page, "_carole_snapshot_id", None):
                raise ValueError("Stale snapshot")

        if ref is None and selector:
            clean = str(selector).strip("[] \t\r\n")
            if clean.isdigit():
                ref = clean
                selector = None

        if ref is not None:
            key = str(ref).strip("[] \t\r\n")
            info = getattr(page, "_carole_refs", {}).get(key)
            if info is None:
                raise ValueError("Unknown or stale ref")

            frame = info["frame"]
            if frame.is_detached():
                raise ValueError("Ref frame is detached")

            handle = await frame.evaluate_handle(
                """({token, ref}) => {
                    const snapshot = window.__caroleSnapshot;
                    if (!snapshot || snapshot.token !== token) return null;
                    const node = snapshot.nodes.get(ref);
                    return node && node.isConnected ? node : null;
                }""",
                {"token": info["token"], "ref": info["local_ref"]},
            )
            element = handle.as_element()
            if element is None:
                await handle.dispose()
                raise ValueError("Ref node is detached or document changed")

            return element, True

        if not selector:
            raise ValueError("An element ref or selector is required")

        frame = page
        if frame_index is not None:
            frames = [f for f in page.frames if f is not page.main_frame]
            if not 0 <= frame_index < len(frames):
                raise ValueError("frame_index out of range")
            frame = frames[frame_index]

        locator = frame.locator(selector)
        if await locator.count() != 1:
            raise ValueError("Selector must match exactly one element")

        return locator, False

    @_session_method
    async def navigate(
        self, url: str, agent_id: str, agent_name: str, team_id: str,
        wait_until: str = "domcontentloaded",
    ) -> str:
        page = await _get_page(agent_id)
        self._invalidate_refs(page)

        response = await page.goto(
            _safe_url(url), wait_until=wait_until, timeout=30_000
        )
        readiness = await _wait_for_page_readiness(
            page, agent_id, agent_name, team_id
        )
        await _publish_screenshot(
            page, agent_id, agent_name, team_id, "Navigated"
        )

        snapshot = await self._build_snapshot_text(page)
        status = response.status if response else None

        return (
            f"Navigation status={status}; readiness={readiness}\n"
            f"URL: {page.url}\nTitle: {await page.title()}\n{snapshot}"
        )

    @_session_method
    async def snapshot(
        self, agent_id: str, agent_name: str = "Agent",
        team_id: str = "default", include_screenshot: bool = True,
    ) -> str:
        page = await _get_page(agent_id)
        text = await self._build_snapshot_text(page)

        if include_screenshot:
            await _publish_screenshot(
                page, agent_id, agent_name, team_id, "Snapshot"
            )

        return (
            f"Page: {page.url}\n"
            f"Title: {await page.title()}\n"
            f"Snapshot ID: {page._carole_snapshot_id}\n\n{text}"
        )

    @_session_method
    async def act(
        self, kind: str, agent_id: str, agent_name: str, team_id: str,
        ref: Optional[int] = None,
        selector: Optional[str] = None,
        text: Optional[str] = None,
        key: Optional[str] = None,
        value: Optional[str] = None,
        x: Optional[float] = None,
        y: Optional[float] = None,
        frame_index: Optional[int] = None,
        slow_type: bool = False,
        snapshot_id: Optional[str] = None,
    ) -> str:
        page = await _get_page(agent_id)
        target = None
        dispose = False

        element_actions = {
            "click", "type", "clear", "hover", "select", "check", "uncheck"
        }
        non_element_actions = {"press", "scroll_down", "scroll_up", "coords"}

        if kind not in element_actions | non_element_actions:
            raise ValueError("Unknown action")

        if snapshot_id is not None:
            if snapshot_id != getattr(page, "_carole_snapshot_id", None):
                raise ValueError("Snapshot belongs to a different state or tab")

        try:
            if kind in element_actions:
                target, dispose = await self._target(
                    page, ref, selector, frame_index, snapshot_id
                )

            # Invalidate before acting, including when the action later times out.
            # A timed-out click can still have triggered a side effect.
            self._invalidate_refs(page)

            if kind == "click":
                await target.click(timeout=10_000)
            elif kind == "type":
                if not isinstance(text, str):
                    raise ValueError("type requires string text")
                if slow_type:
                    await target.fill("", timeout=10_000)
                    await target.type(text, delay=40, timeout=15_000)
                else:
                    await target.fill(text, timeout=10_000)
            elif kind == "clear":
                await target.fill("", timeout=10_000)
            elif kind == "hover":
                await target.hover(timeout=10_000)
            elif kind == "select":
                if not isinstance(value, str):
                    raise ValueError("select requires string value")
                # Empty-string option values are valid.
                try:
                    selected = await target.select_option(
                        value=value, timeout=4_000
                    )
                except Exception:
                    selected = await target.select_option(
                        label=value, timeout=4_000
                    )
                if not selected:
                    raise ValueError("No option selected")
            elif kind == "check":
                await target.check(timeout=10_000)
            elif kind == "uncheck":
                await target.uncheck(timeout=10_000)
            elif kind == "press":
                if not isinstance(key, str) or not key:
                    raise ValueError("press requires key")
                await page.keyboard.press(key)
            elif kind == "scroll_down":
                await page.evaluate("window.scrollBy(0, 600)")
            elif kind == "scroll_up":
                await page.evaluate("window.scrollBy(0, -600)")
            elif kind == "coords":
                if x is None or y is None:
                    raise ValueError("coords requires x and y")
                await page.mouse.click(float(x), float(y))

        finally:
            if dispose and target is not None:
                await target.dispose()

        # A click may have opened a new active tab.
        page = await _get_page(agent_id)
        self._setup_dialog_handler(page, agent_id)

        await _publish_screenshot(
            page, agent_id, agent_name, team_id, f"act:{kind}"
        )
        return (
            f"Action {kind} executed. URL: {page.url}. "
            "Take a fresh snapshot to verify the outcome."
        )

    @_session_method
    async def handle_dialog(
        self, agent_id: str, accept: bool = True, prompt_text: str = "",
    ) -> str:
        """
        Preconfigure the NEXT dialog, expiring after 30 seconds.

        Dialogs are never left pending because they can block the action that
        triggered them. This method cannot accept an already-dismissed dialog.
        """
        page = await _get_page(agent_id)
        page._carole_next_dialog = {
            "accept": bool(accept),
            "prompt_text": prompt_text,
            "expires": time.monotonic() + 30,
        }
        return (
            "Configured the next dialog response for 30 seconds: "
            + ("accept." if accept else "dismiss.")
        )

    async def _navigation_action(
        self, action, agent_id, agent_name, team_id,
    ):
        page = await _get_page(agent_id)
        self._invalidate_refs(page)
        await getattr(page, action)(
            wait_until="domcontentloaded", timeout=30_000
        )
        readiness = await _wait_for_page_readiness(
            page, agent_id, agent_name, team_id
        )
        await _publish_screenshot(
            page, agent_id, agent_name, team_id, action
        )
        return f"{action}: {page.url}; readiness={readiness}"

    @_session_method
    async def go_back(self, agent_id, agent_name, team_id):
        return await self._navigation_action(
            "go_back", agent_id, agent_name, team_id
        )

    @_session_method
    async def go_forward(self, agent_id, agent_name, team_id):
        return await self._navigation_action(
            "go_forward", agent_id, agent_name, team_id
        )

    @_session_method
    async def reload(self, agent_id, agent_name, team_id):
        return await self._navigation_action(
            "reload", agent_id, agent_name, team_id
        )

    @_session_method
    async def get_current_url(self, agent_id):
        return f"Current URL: {(await _get_page(agent_id)).url}"

    @_session_method
    async def screenshot(
        self, agent_id, agent_name, team_id, full_page=False,
    ):
        # Streaming is deliberately viewport-only to limit data exposure/size.
        page = await _get_page(agent_id)
        await _publish_screenshot(
            page, agent_id, agent_name, team_id, "Screenshot"
        )
        return "Screenshot capture/stream attempted (viewport only)."

    async def _read_target(self, selector, agent_id, operation, *args):
        page = await _get_page(agent_id)
        target, dispose = await self._target(
            page, selector=selector or "body"
        )
        try:
            return await getattr(target, operation)(*args)
        finally:
            if dispose:
                await target.dispose()

    @_session_method
    async def extract_text(self, selector, agent_id):
        text = await self._read_target(selector, agent_id, "inner_text")
        return text[:MAX_TEXT_CHARS] or "No text found."

    @_session_method
    async def extract_html(self, selector, agent_id):
        if not selector:
            html = await (await _get_page(agent_id)).content()
        else:
            html = await self._read_target(
                selector, agent_id, "inner_html"
            )
        return html[:MAX_HTML_CHARS]

    @_session_method
    async def get_attribute(self, selector, attribute, agent_id):
        value = await self._read_target(
            selector, agent_id, "get_attribute", attribute
        )
        return json.dumps(value)

    @_session_method
    async def evaluate_js(self, script, agent_id):
        # Keep this tool out of untrusted/autonomous tool registries.
        # It can read secrets and perform arbitrary authenticated page actions.
        from core.llm.config_manager import load_config
        cfg = (load_config() or {}).get("browser_automation") or {}
        if cfg.get("allow_evaluate_js") is not True:
            return "Error: arbitrary JavaScript execution is disabled."

        result = await (await _get_page(agent_id)).evaluate(script)
        return json.dumps(result, default=str, ensure_ascii=False)[:3000]

    @_session_method
    async def get_all_links(self, agent_id, limit=30):
        page = await _get_page(agent_id)
        links = await page.locator("a[href]").evaluate_all(
            """nodes => nodes.slice(0, 500).map(a => ({
                text: (a.innerText || "").trim().slice(0, 100),
                href: a.href
            }))"""
        )
        # Do not label list indexes as actionable snapshot refs.
        return json.dumps(links[:max(0, min(int(limit), 100))])

    @_session_method
    async def get_page_metadata(self, agent_id):
        page = await _get_page(agent_id)
        data = await page.evaluate(
            """() => ({
                title: document.title,
                url: location.href,
                description:
                    document.querySelector('meta[name="description"]')
                        ?.content || "",
                links: document.links.length,
                images: document.images.length
            })"""
        )
        return json.dumps(data, ensure_ascii=False)

    @_session_method
    async def wait_for_selector(
        self, selector, agent_id, timeout_ms=10000,
    ):
        page = await _get_page(agent_id)
        await page.locator(selector).wait_for(
            state="visible",
            timeout=max(1, min(int(timeout_ms), 30_000)),
        )
        return "Element is visible."

    @_session_method
    async def wait_for_navigation(self, agent_id, timeout_ms=10000):
        page = await _get_page(agent_id)
        await page.wait_for_load_state(
            "domcontentloaded",
            timeout=max(1, min(int(timeout_ms), 30_000)),
        )
        return (
            f"Current document reached DOMContentLoaded: {page.url}. "
            "This does not prove a new navigation occurred."
        )

    @_session_method
    async def wait_ms(self, ms, agent_id):
        ms = max(0, min(int(ms), 30_000))
        await asyncio.sleep(ms / 1000)
        return f"Waited {ms}ms."

    @_session_method
    async def get_cookies(self, agent_id):
        cookies = await (await _get_page(agent_id)).context.cookies()
        # Cookie values are authentication material; omit them.
        return json.dumps([
            {
                "name": cookie["name"],
                "domain": cookie.get("domain"),
                "secure": cookie.get("secure"),
                "httpOnly": cookie.get("httpOnly"),
            }
            for cookie in cookies[:100]
        ])

    @_session_method
    async def clear_cookies(self, agent_id):
        await (await _get_page(agent_id)).context.clear_cookies()
        return "Cookies cleared."

    @_session_method
    async def open_new_tab(self, url, agent_id, agent_name, team_id):
        from core.tools.browser_pool import get_new_page

        url = _safe_url(url)
        page = await get_new_page(agent_id)
        self._setup_dialog_handler(page, agent_id)
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await _publish_screenshot(
            page, agent_id, agent_name, team_id, "New tab"
        )
        return f"Opened and activated new tab: {page.url}"

    @_session_method
    async def switch_tab(self, index, agent_id, agent_name, team_id):
        from core.tools.browser_pool import set_active_page

        page = await _get_page(agent_id)
        pages = page.context.pages
        if not 0 <= int(index) < len(pages):
            raise ValueError("Tab index out of range")

        target = pages[int(index)]
        await set_active_page(agent_id, target)
        self._invalidate_refs(target)
        self._setup_dialog_handler(target, agent_id)
        await target.bring_to_front()
        await _publish_screenshot(
            target, agent_id, agent_name, team_id, "Switched tab"
        )
        return f"Active tab: {target.url}"

    @_session_method
    async def close_tab(self, index, agent_id):
        page = await _get_page(agent_id)
        context = page.context
        pages = context.pages
        if not 0 <= int(index) < len(pages):
            raise ValueError("Tab index out of range")

        await pages[int(index)].close()
        return f"Tab closed; {len(context.pages)} tab(s) remain."

    @_session_method
    async def list_tabs(self, agent_id):
        page = await _get_page(agent_id)
        return json.dumps([
            {"index": i, "url": p.url, "active": p is page}
            for i, p in enumerate(page.context.pages)
        ])

    async def close_browser(self, agent_id):
        # Do not decorate: closing a session while holding it is forbidden.
        from core.tools.browser_pool import close_agent_browser
        try:
            closed = await close_agent_browser(agent_id)
            return "Session closed." if closed else "No browser session."
        except RuntimeError:
            return "Error: session is active; stop its browsing task first."

    async def get_interactive_elements(self, agent_id, selector_scope=""):
        return await self.snapshot(
            agent_id, include_screenshot=False
        )

    @_session_method
    async def screenshot_element(
        self, selector, agent_id, agent_name, team_id,
    ):
        # Use the masked viewport screenshot instead of accidentally exposing
        # the contents of a credential element.
        page = await _get_page(agent_id)
        target, dispose = await self._target(page, selector=selector)
        try:
            await target.scroll_into_view_if_needed(timeout=10_000)
        finally:
            if dispose:
                await target.dispose()

        await _publish_screenshot(
            page, agent_id, agent_name, team_id, "Element viewport"
        )
        return "Element scrolled into view; masked screenshot attempted."

    @_session_method
    async def find_elements(self, selector, agent_id, limit=20):
        page = await _get_page(agent_id)
        clean = str(selector).strip("[] \t\r\n")

        if clean.isdigit():
            text = await self._read_target(selector, agent_id, "inner_text")
            return json.dumps([{"text": text[:200]}])

        locator = page.locator(selector)
        count = await locator.count()
        result = []
        for i in range(min(count, max(0, min(int(limit), 100)))):
            item = locator.nth(i)
            result.append({
                "index": i,
                "text": (await item.inner_text())[:200],
                "tag": await item.evaluate("el => el.localName"),
            })
        return json.dumps({"count": count, "elements": result})

    @_session_method
    async def scroll_to_element(self, selector, agent_id):
        page = await _get_page(agent_id)
        target, dispose = await self._target(page, selector=selector)
        try:
            await target.scroll_into_view_if_needed(timeout=10_000)
        finally:
            if dispose:
                await target.dispose()
        self._invalidate_refs(page)
        return "Element scrolled into view."

    @_session_method
    async def switch_to_frame(self, frame_index, agent_id):
        page = await _get_page(agent_id)
        frames = [f for f in page.frames if f is not page.main_frame]
        if not 0 <= int(frame_index) < len(frames):
            raise ValueError("Frame index out of range")
        frame = frames[int(frame_index)]
        return (
            f"Frame URL={frame.url}, name={frame.name}. "
            "No persistent frame switch was performed. "
            "Use snapshot refs or act(frame_index=...)."
        )

    @_session_method
    async def scroll(self, direction, amount, agent_id, selector=""):
        vectors = {
            "down": (0, 1), "up": (0, -1),
            "right": (1, 0), "left": (-1, 0),
        }
        if direction not in vectors:
            raise ValueError("Unknown scroll direction")

        amount = max(0, min(int(amount), 10_000))
        dx, dy = vectors[direction]
        delta = [dx * amount, dy * amount]
        page = await _get_page(agent_id)

        if selector:
            target, dispose = await self._target(page, selector=selector)
            try:
                await target.evaluate(
                    "(el, [x, y]) => el.scrollBy(x, y)", delta
                )
            finally:
                if dispose:
                    await target.dispose()
        else:
            await page.evaluate(
                "([x, y]) => window.scrollBy(x, y)", delta
            )

        self._invalidate_refs(page)
        return "Scrolled."

    # Legacy entry points delegate to the same safe dispatcher.

    async def click(
        self, selector, agent_id, agent_name="", team_id="",
    ):
        return await self.act(
            "click", agent_id, agent_name, team_id, selector=selector
        )

    @_session_method
    async def click_text(
        self, text, agent_id, agent_name="", team_id="",
    ):
        page = await _get_page(agent_id)
        locator = page.get_by_text(text, exact=True)
        if await locator.count() != 1:
            raise ValueError("Text must match exactly one element")

        self._invalidate_refs(page)
        await locator.click(timeout=10_000)
        await _publish_screenshot(
            page, agent_id, agent_name, team_id, "Clicked text"
        )
        return "Click executed; verify with a snapshot."

    @_session_method
    async def type_text(
        self, selector, text, agent_id, clear_first=True,
    ):
        page = await _get_page(agent_id)
        target, dispose = await self._target(page, selector=selector)
        self._invalidate_refs(page)
        try:
            if clear_first:
                await target.fill(text, timeout=10_000)
            else:
                await target.type(text, delay=40, timeout=15_000)
        finally:
            if dispose:
                await target.dispose()
        return "Text entered."

    async def press_key(self, key, agent_id):
        return await self.act("press", agent_id, "", "", key=key)

    async def hover(
        self, selector, agent_id, agent_name="", team_id="",
    ):
        return await self.act(
            "hover", agent_id, agent_name, team_id, selector=selector
        )

    async def select_option(self, selector, value, agent_id):
        return await self.act(
            "select", agent_id, "", "", selector=selector, value=value
        )

    async def check_checkbox(self, selector, checked, agent_id):
        return await self.act(
            "check" if checked else "uncheck",
            agent_id, "", "", selector=selector,
        )


browser_tool = BrowserTool()