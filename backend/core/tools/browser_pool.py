"""
Shared Playwright pool.

Concurrency contract:
- All Playwright operations run on one owning asyncio event loop.
- browser_session() serializes operations per agent.
- Nested sessions in the same task are supported.
- Active sessions are pinned and cannot be evicted.
- Idle contexts use actual LRU ordering.

Callers performing multiple related operations should hold browser_session()
for the entire sequence, not just call get_page().
"""

import asyncio
import inspect
import logging
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("carole.browser_pool")

MAX_BROWSER_CONTEXTS = 5


@dataclass
class _Session:
    context: Any
    page: Any = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    owner: Any = None
    users: int = 0  # Includes tasks waiting for this session's lock.


_playwright: Any = None
_browser: Any = None
_owner_loop: Any = None
_lock: Optional[asyncio.Lock] = None

_sessions: "OrderedDict[str, _Session]" = OrderedDict()
_headless_override: Optional[bool] = None
_restart_requested = False
_shutting_down = False


def _get_lock() -> asyncio.Lock:
    global _lock, _owner_loop

    loop = asyncio.get_running_loop()
    if _owner_loop is not None and _owner_loop is not loop:
        raise RuntimeError(
            "Browser pool belongs to another event loop. "
            "Submit browser work to its owning loop; do not reuse Playwright "
            "objects across threads or asyncio.run() calls."
        )

    if _lock is None:
        _owner_loop = loop
        _lock = asyncio.Lock()

    return _lock


def set_headless_mode(headless: Optional[bool]) -> None:
    """
    Request a mode change.

    Must be called on the pool's owning loop after initialization.
    The browser is restarted lazily when no sessions are active.
    """
    global _headless_override, _restart_requested

    if headless is not None and type(headless) is not bool:
        raise TypeError("headless must be bool or None")

    if _owner_loop is not None:
        if asyncio.get_running_loop() is not _owner_loop:
            raise RuntimeError("set_headless_mode must run on the owning loop")

    if _headless_override != headless:
        _headless_override = headless
        _restart_requested = True


async def _safe_close(resource: Any, method: str = "close") -> None:
    if resource is None:
        return
    try:
        fn = getattr(resource, method, None)
        if fn is None:
            return
        res = fn()
        if inspect.isawaitable(res):
            await asyncio.wait_for(res, timeout=10)
    except Exception:
        logger.warning("Browser resource cleanup failed", exc_info=True)


async def _ensure_browser():
    """Backward compatibility helper for tests and callers expecting _ensure_browser()."""
    async with _get_lock():
        await _ensure_locked()
        return _browser


async def _dispose_locked() -> None:
    global _browser, _playwright

    sessions = list(_sessions.values())
    _sessions.clear()

    for session in sessions:
        await _safe_close(session.context)

    browser, playwright = _browser, _playwright
    _browser = None
    _playwright = None

    await _safe_close(browser)
    await _safe_close(playwright, "stop")


def _connected() -> bool:
    try:
        return _browser is not None and _browser.is_connected()
    except Exception:
        return False


async def _launch_locked() -> None:
    global _browser, _playwright, _restart_requested

    import os
    from playwright.async_api import async_playwright
    from core.llm.config_manager import load_config, get_browser_key, has_user_configured_keys

    raw_cfg = load_config() or {}
    cfg = raw_cfg.get("browser_automation") or {}
    infrastructure = (
        cfg.get("infrastructure") or cfg.get("provider") or "local"
    )

    if _headless_override is not None:
        headless = _headless_override
    else:
        cfg_display = cfg.get("display_mode")
        cfg_headless = cfg.get("headless")
        if cfg_display is not None or cfg_headless is not None:
            headless = (cfg_display != "windowed" and cfg_headless is not False)
        elif not has_user_configured_keys(raw_cfg):
            env = os.getenv("HEADLESS")
            if env is None:
                env = os.getenv("BROWSER_HEADLESS")
            if env is not None:
                headless = env.strip().lower() not in {
                    "0", "false", "no", "headed", "windowed"
                }
            else:
                headless = True
        else:
            headless = True

    try:
        _playwright = await async_playwright().start()

        if infrastructure == "browserbase":
            from urllib.parse import urlencode

            key = get_browser_key(raw_cfg, "browserbase", "BROWSERBASE_API_KEY")
            if not key:
                raise RuntimeError("Browserbase API key is not configured")

            params = {"apiKey": key}
            project_id = cfg.get("project_id") or os.getenv("BROWSERBASE_PROJECT_ID")
            if project_id and str(project_id).strip():
                params["projectId"] = str(project_id).strip()

            endpoint = (
                "wss://connect.browserbase.com?"
                + urlencode(params)
            )
            # Fail explicitly instead of silently changing infrastructure; retry transient connect blips
            last_conn_err = None
            for attempt in range(2):
                try:
                    _browser = await _playwright.chromium.connect_over_cdp(
                        endpoint, timeout=30_000
                    )
                    break
                except Exception as conn_err:
                    last_conn_err = conn_err
                    if attempt == 0:
                        await asyncio.sleep(0.5)
            if _browser is None and last_conn_err:
                raise last_conn_err
        else:
            proxy = None
            provider = cfg.get("proxy_provider") or infrastructure

            if provider == "scraperapi":
                key = get_browser_key(raw_cfg, "scraperapi", "SCRAPERAPI_KEY")
                if not key:
                    raise RuntimeError("ScraperAPI key is not configured")
                proxy = {
                    "server": "http://proxy-server.scraperapi.com:8001",
                    "username": "scraperapi",
                    "password": key,
                }
            elif provider == "zenrows":
                key = get_browser_key(raw_cfg, "zenrows", "ZENROWS_KEY")
                if not key:
                    raise RuntimeError("ZenRows key is not configured")
                proxy = {
                    "server": "http://proxy.zenrows.com:8001",
                    "username": key,
                    "password": "",
                }

            _browser = await _playwright.chromium.launch(
                headless=headless,
                proxy=proxy,
                args=["--disable-dev-shm-usage", "--window-size=1280,900"],
                timeout=30_000,
            )

        _restart_requested = False
        logger.info("Browser started: infrastructure=%s", infrastructure)

    except BaseException:
        await _dispose_locked()
        raise


async def _ensure_locked() -> None:
    if _shutting_down:
        raise RuntimeError("Browser pool is shutting down")

    busy = any(session.users for session in _sessions.values())

    if _connected():
        if not _restart_requested or busy:
            return
        await _dispose_locked()

    elif busy:
        # Do not recreate the browser underneath in-flight actions.
        raise RuntimeError(
            "Browser disconnected during an active session. Retry the task."
        )
    else:
        await _dispose_locked()

    await _launch_locked()


async def _install_network_guard(context: Any, cfg: Dict[str, Any]) -> None:
    from core.tools.ssrf_guard import assert_safe_public_url

    # Explicit opt-in only. Prefer a narrow host allowlist in ssrf_guard.
    allow_local = cfg.get("allow_local_urls") is True

    async def guard(route: Any) -> None:
        try:
            from core.llm.config_manager import load_config
            cur_cfg = (load_config() or {}).get("browser_automation") or {}
            cur_allow_local = allow_local or (cur_cfg.get("allow_local_urls") is True)
            assert_safe_public_url(
                route.request.url, allow_local=cur_allow_local
            )
        except Exception:
            await route.abort("blockedbyclient")
            return

        await route.continue_()

    # Context-wide routing covers new tabs and iframe requests too.
    # Service workers are blocked during context creation.
    await context.route("**/*", guard)


async def _get_session_locked(agent_id: str) -> _Session:
    if not isinstance(agent_id, str) or not agent_id:
        raise ValueError("agent_id must be a nonempty string")

    await _ensure_locked()

    existing = _sessions.get(agent_id)
    if existing is not None:
        _sessions.move_to_end(agent_id)
        return existing

    if len(_sessions) >= MAX_BROWSER_CONTEXTS:
        victim_id = next(
            (
                key for key, session in _sessions.items()
                if session.users == 0
            ),
            None,
        )
        if victim_id is None:
            raise RuntimeError(
                "Browser capacity reached; all sessions are active. "
                "Retry after another browsing task finishes."
            )

        victim = _sessions.pop(victim_id)
        await _safe_close(victim.context)

    from core.llm.config_manager import load_config
    cfg = (load_config() or {}).get("browser_automation") or {}

    context = await _browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale=cfg.get("locale", "en-US"),
        timezone_id=cfg.get("timezone_id", "UTC"),
        permissions=[],
        service_workers="block",
        accept_downloads=True,
    )

    try:
        t1 = context.set_default_timeout(10_000)
        if inspect.isawaitable(t1):
            await t1
        t2 = context.set_default_navigation_timeout(30_000)
        if inspect.isawaitable(t2):
            await t2
        await _install_network_guard(context, cfg)
    except BaseException:
        await _safe_close(context)
        raise

    session = _Session(context=context)
    _sessions[agent_id] = session

    def on_page(page: Any) -> None:
        # New tabs/popups become the active page.
        session.page = page
        err_res = page.on(
            "pageerror",
            lambda exc: logger.debug("Page JavaScript error: %s", type(exc).__name__),
        )
        if inspect.isawaitable(err_res):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(err_res)
            except RuntimeError:
                pass

    res_on = context.on("page", on_page)
    if inspect.isawaitable(res_on):
        await res_on
    return session


async def get_page(agent_id: str) -> Any:
    """
    Return the active page.

    For safety across awaits, use browser_session() around related calls.
    """
    async with _get_lock():
        session = await _get_session_locked(agent_id)

        if session.page is not None and not session.page.is_closed():
            return session.page

        pages = [page for page in session.context.pages if not page.is_closed()]
        if pages:
            session.page = pages[-1]
        else:
            session.page = await session.context.new_page()

        return session.page


@asynccontextmanager
async def browser_session(agent_id: str):
    """Pin a session and serialize operations, with same-task reentrancy."""
    task = asyncio.current_task()

    async with _get_lock():
        session = await _get_session_locked(agent_id)
        session.users += 1
        nested = session.owner is task

    acquired = False
    try:
        if not nested:
            await session.lock.acquire()
            acquired = True
            session.owner = task

        yield await get_page(agent_id)

    finally:
        if acquired:
            session.owner = None
            session.lock.release()

        async with _get_lock():
            session.users -= 1


async def get_new_page(agent_id: str) -> Any:
    async with browser_session(agent_id):
        async with _get_lock():
            session = _sessions[agent_id]
            session.page = await session.context.new_page()
            return session.page


async def set_active_page(agent_id: str, page: Any) -> None:
    async with _get_lock():
        session = _sessions.get(agent_id)
        if session is None or page.context is not session.context:
            raise ValueError("Page does not belong to this agent")
        if page.is_closed():
            raise ValueError("Cannot activate a closed page")

        session.page = page
        _sessions.move_to_end(agent_id)


async def close_agent_browser(agent_id: str) -> bool:
    async with _get_lock():
        session = _sessions.get(agent_id)
        if session is None:
            return False
        if session.users:
            raise RuntimeError("Cannot close an active browser session")

        _sessions.pop(agent_id)
        await _safe_close(session.context)
        return True


async def get_active_agents() -> list:
    async with _get_lock():
        return list(_sessions)


async def get_cdp_session(agent_id: str) -> Any:
    """
    Create and return a new Chrome DevTools Protocol (CDP) session for the active page.
    Enables low-level CDP screencasting, network tracing, and debugging.
    """
    page = await get_page(agent_id)
    if hasattr(page, "context") and hasattr(page.context, "new_cdp_session"):
        return await page.context.new_cdp_session(page)
    return None


async def close_all() -> None:
    """
    Call after stopping/cancelling browser jobs during server shutdown.

    Refuses to destroy sessions still executing.
    """
    global _owner_loop, _lock, _shutting_down

    lock = _get_lock()
    async with lock:
        if any(session.users for session in _sessions.values()):
            raise RuntimeError(
                "Cancel and await active browser jobs before close_all()"
            )

        _shutting_down = True
        try:
            await _dispose_locked()
        finally:
            _shutting_down = False

    # Allows a clean restart on a subsequent event loop after full shutdown.
    _owner_loop = None
    _lock = None


class _ContextsProxy(dict):
    """Backward-compatible proxy mapping agent_id -> context for tests and metrics."""
    def __contains__(self, key):
        return key in _sessions
    def __getitem__(self, key):
        return _sessions[key].context
    def __len__(self):
        return len(_sessions)
    def __iter__(self):
        return iter(_sessions)
    def clear(self):
        _sessions.clear()
    def get(self, key, default=None):
        if key in _sessions:
            return _sessions[key].context
        return default
    def pop(self, key, default=None):
        sess = _sessions.pop(key, None)
        return sess.context if sess else default
    def keys(self):
        return _sessions.keys()
    def values(self):
        return [s.context for s in _sessions.values()]
    def items(self):
        return [(k, s.context) for k, s in _sessions.items()]


_contexts = _ContextsProxy()

# Compatibility with existing module-style imports.
import sys
browser_pool = sys.modules[__name__]