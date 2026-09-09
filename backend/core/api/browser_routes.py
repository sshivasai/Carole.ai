"""
# backend/core/api/browser_routes.py

API routes for real-time interactive browser takeover and CDP screencast streaming.
Supports low-latency WebSocket live video streaming, direct canvas interactions,
element reference clicks, and human-in-the-loop intervention resolution.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, Dict, Any
import asyncio
import base64
import inspect
import json
import logging

from core.auth.auth_middleware import require_auth
from core.tools.browser_tool import browser_tool, _get_page, _publish_screenshot
from core.tools.interaction_tools import pending_questions, question_answers
from core.memory.database import async_session
from core.api.crud_routes import _assert_agent_access, _assert_team_access


async def _owned_browser(agent_id, user):
    if not agent_id or agent_id == "global":
        raise HTTPException(400, "An owned agent is required")
    async with async_session() as db:
        await _assert_agent_access(db, agent_id, user["sub"])

logger = logging.getLogger("carole.browser_routes")

router = APIRouter(prefix="/api/browser", tags=["browser"])


class BrowserActRequest(BaseModel):
    agent_id: Optional[str] = "global"
    kind: str  # click, coords, type, clear, hover, press, scroll_down, scroll_up, navigate, go_back, reload
    x: Optional[float] = None
    y: Optional[float] = None
    text: Optional[str] = None
    key: Optional[str] = None
    ref: Optional[int] = None
    selector: Optional[str] = None
    url: Optional[str] = None


class ResolveHILRequest(BaseModel):
    question_id: str
    answer: str = "Solved by user"


@router.post("/act")
async def browser_act_direct(
    body: BrowserActRequest,
    user: dict = Depends(require_auth),
):
    """
    Direct interactive browser action dispatcher for frontend Canvas takeover.
    Supports normalized coordinate clicks, element refs, CSS selectors, typing, and navigation.
    """
    await _owned_browser(body.agent_id, user)
    try:
        page = await _get_page(body.agent_id)
        kind = body.kind.lower()

        if body.ref is not None:
            # Target action by snapshot DOM element reference
            target, dispose = await browser_tool._target(page, ref=body.ref)
            try:
                if kind in ("click", "coords"):
                    await target.click(timeout=5000)
                elif kind == "type" and body.text is not None:
                    await target.fill(body.text, timeout=5000)
                elif kind == "clear":
                    await target.fill("", timeout=5000)
                elif kind == "hover":
                    await target.hover(timeout=5000)
                else:
                    return {"status": "error", "message": f"Unsupported ref action '{kind}'."}
            finally:
                if dispose:
                    await target.dispose()

        elif kind == "coords" and body.x is not None and body.y is not None:
            # Click at exact normalized viewport coordinates
            await page.mouse.click(float(body.x), float(body.y))
        elif kind == "click":
            if body.selector:
                await page.click(body.selector, timeout=5000)
            elif body.x is not None and body.y is not None:
                await page.mouse.click(float(body.x), float(body.y))
            else:
                return {"status": "error", "message": "Click requires selector, ref, or coords (x, y)."}
        elif kind == "type" and body.text is not None:
            if body.selector:
                await page.fill(body.selector, body.text)
            else:
                await page.keyboard.type(body.text)
        elif kind == "press" and body.key:
            await page.keyboard.press(body.key)
        elif kind == "scroll_down":
            await page.evaluate("window.scrollBy(0, 500)")
        elif kind == "scroll_up":
            await page.evaluate("window.scrollBy(0, -500)")
        elif kind == "go_back":
            if hasattr(page, "go_back"):
                await page.go_back(wait_until="domcontentloaded", timeout=15000)
        elif kind == "reload":
            if hasattr(page, "reload"):
                await page.reload(wait_until="domcontentloaded", timeout=15000)
        elif kind == "navigate" and body.url:
            from core.tools.ssrf_guard import assert_safe_public_url
            try:
                safe_url = assert_safe_public_url(body.url, allow_local=True)
            except Exception as ssrf_err:
                raise HTTPException(status_code=400, detail=f"URL access denied: {ssrf_err}")
            await page.goto(safe_url, wait_until="domcontentloaded", timeout=20000)
        else:
            return {"status": "error", "message": f"Unsupported or incomplete action '{kind}'."}

        # Small delay for page rendering after interaction
        await asyncio.sleep(0.2)

        # Capture updated screenshot
        screenshot_bytes = await page.screenshot(type="jpeg", quality=60)
        b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        title_str = await page.title() if hasattr(page, "title") else ""

        return {
            "status": "success",
            "url": getattr(page, "url", ""),
            "title": title_str,
            "screenshot": f"data:image/jpeg;base64,{b64}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[BrowserRoutes] Direct action '%s' failed: %s", body.kind, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screenshot")
async def get_browser_screenshot(
    agent_id: str = Query("global"),
    user: dict = Depends(require_auth),
):
    """
    Fetches the current live screenshot of the browser page for an agent.
    """
    await _owned_browser(agent_id, user)
    try:
        page = await _get_page(agent_id)
        screenshot_bytes = await page.screenshot(type="jpeg", quality=60)
        b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        title_str = await page.title() if hasattr(page, "title") else ""
        return {
            "status": "success",
            "url": getattr(page, "url", ""),
            "title": title_str,
            "screenshot": f"data:image/jpeg;base64,{b64}",
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "screenshot": None}


@router.post("/resolve-hil")
async def resolve_browser_hil(
    body: ResolveHILRequest,
    user: dict = Depends(require_auth),
):
    """
    Resolves an active human-in-the-loop takeover request from in-chat card or canvas.
    """
    q_id = body.question_id
    from core.tools.interaction_tools import pending_question_details
    details = pending_question_details.get(q_id)
    if not details or not details.get("team_id"):
        raise HTTPException(404, "Intervention not found")
    async with async_session() as db:
        await _assert_team_access(db, str(details["team_id"]), user["sub"])
    if q_id in pending_questions:
        question_answers[q_id] = body.answer
        pending_questions[q_id].set()
        return {"status": "success", "message": "Intervention marked as resolved."}
    return {"status": "not_found", "message": "Question event has already completed or expired."}


@router.websocket("/stream")
async def browser_stream_websocket(
    websocket: WebSocket,
    agent_id: str = Query("global"),
    ticket: str = Query(""),
):
    """
    High-performance real-time WebSocket screencast stream.
    Leverages Chromium's native CDP Page.startScreencast with drop-oldest frame backpressure,
    and supports bidirectional direct interactive takeover from frontend Canvas.
    """
    from core.auth.auth_service import auth_service
    user_id = auth_service.verify_ws_ticket(ticket) if ticket else None
    if not user_id:
        await websocket.close(code=4001)
        return
    try:
        async with async_session() as db:
            user = await auth_service.get_active_user(db, user_id)
            if not user:
                raise HTTPException(401, "Inactive user")
        await _owned_browser(agent_id, {"sub": str(user_id)})
    except HTTPException:
        await websocket.close(code=4003)
        return
    await websocket.accept()
    cdp = None
    screencast_active = False
    stop_event = asyncio.Event()
    frame_queue = asyncio.Queue(maxsize=2)  # drop-oldest queue to eliminate latency lag

    async def sender_loop():
        while not stop_event.is_set():
            try:
                frame_data = await frame_queue.get()
                await websocket.send_text(json.dumps(frame_data))
            except asyncio.CancelledError:
                break
            except Exception:
                break

    sender_task = asyncio.create_task(sender_loop())
    fallback_task = None

    try:
        page = await _get_page(agent_id)

        # Attempt native CDP screencasting if running under Chromium
        if hasattr(page, "context") and hasattr(page.context, "new_cdp_session"):
            try:
                cdp = await page.context.new_cdp_session(page)

                async def on_screencast_frame(event):
                    if stop_event.is_set():
                        return
                    session_id = event.get("sessionId")
                    b64_data = event.get("data", "")

                    if session_id is not None and cdp:
                        try:
                            await cdp.send("Page.screencastFrameAck", {"sessionId": session_id})
                        except Exception:
                            pass

                    frame_payload = {
                        "type": "frame",
                        "image": f"data:image/jpeg;base64,{b64_data}",
                        "url": getattr(page, "url", ""),
                        "title": await page.title() if hasattr(page, "title") else "",
                    }
                    if frame_queue.full():
                        try:
                            frame_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    try:
                        frame_queue.put_nowait(frame_payload)
                    except asyncio.QueueFull:
                        pass

                res_cdp_on = cdp.on("Page.screencastFrame", on_screencast_frame)
                if inspect.isawaitable(res_cdp_on):
                    await res_cdp_on
                await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 60, "everyNthFrame": 1})
                screencast_active = True

                await websocket.send_text(json.dumps({
                    "type": "connected",
                    "mode": "cdp",
                    "url": getattr(page, "url", ""),
                }))
            except Exception as cdp_err:
                logger.debug("CDP Screencast not available: %s. Using periodic capture.", cdp_err)
                cdp = None

        if not screencast_active:
            # Fallback periodic screenshot streaming if CDP is unavailable (e.g. mocked in tests)
            await websocket.send_text(json.dumps({
                "type": "connected",
                "mode": "snapshot",
                "url": getattr(page, "url", ""),
            }))

            async def fallback_loop():
                while not stop_event.is_set():
                    try:
                        if hasattr(page, "screenshot"):
                            shot = await page.screenshot(type="jpeg", quality=60)
                            b64 = base64.b64encode(shot).decode("utf-8")
                            title_str = await page.title() if hasattr(page, "title") else ""
                            payload = {
                                "type": "frame",
                                "image": f"data:image/jpeg;base64,{b64}",
                                "url": getattr(page, "url", ""),
                                "title": title_str,
                            }
                            if frame_queue.full():
                                try:
                                    frame_queue.get_nowait()
                                except asyncio.QueueEmpty:
                                    pass
                            try:
                                frame_queue.put_nowait(payload)
                            except asyncio.QueueFull:
                                pass
                        await asyncio.sleep(0.4)
                    except asyncio.CancelledError:
                        break
                    except Exception:
                        await asyncio.sleep(1.0)

            fallback_task = asyncio.create_task(fallback_loop())

        # Receive real-time interactive actions over WebSocket
        while not stop_event.is_set():
            data_str = await websocket.receive_text()
            try:
                msg = json.loads(data_str)
            except Exception:
                continue

            msg_type = msg.get("type", "act")
            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            if msg_type == "act":
                kind = str(msg.get("kind", "")).lower()
                try:
                    if msg.get("ref") is not None:
                        target, disp = await browser_tool._target(page, ref=msg["ref"])
                        try:
                            if kind in ("click", "coords"):
                                await target.click(timeout=5000)
                            elif kind == "type" and msg.get("text") is not None:
                                await target.fill(msg["text"], timeout=5000)
                        finally:
                            if disp:
                                await target.dispose()
                    elif kind == "coords" and msg.get("x") is not None and msg.get("y") is not None:
                        await page.mouse.click(float(msg["x"]), float(msg["y"]))
                    elif kind == "click":
                        if msg.get("selector"):
                            await page.click(msg["selector"], timeout=5000)
                        elif msg.get("x") is not None and msg.get("y") is not None:
                            await page.mouse.click(float(msg["x"]), float(msg["y"]))
                    elif kind == "type" and msg.get("text") is not None:
                        if msg.get("selector"):
                            await page.fill(msg["selector"], msg["text"])
                        else:
                            await page.keyboard.type(msg["text"])
                    elif kind == "press" and msg.get("key"):
                        await page.keyboard.press(msg["key"])
                    elif kind == "scroll_down":
                        await page.evaluate("window.scrollBy(0, 500)")
                    elif kind == "scroll_up":
                        await page.evaluate("window.scrollBy(0, -500)")
                    elif kind == "go_back" and hasattr(page, "go_back"):
                        await page.go_back(wait_until="domcontentloaded", timeout=15000)
                    elif kind == "reload" and hasattr(page, "reload"):
                        await page.reload(wait_until="domcontentloaded", timeout=15000)
                    elif kind == "navigate" and msg.get("url"):
                        from core.tools.ssrf_guard import assert_safe_public_url
                        safe = assert_safe_public_url(msg["url"], allow_local=True)
                        await page.goto(safe, wait_until="domcontentloaded", timeout=20000)

                    await websocket.send_text(json.dumps({
                        "type": "action_result",
                        "status": "success",
                        "kind": kind,
                        "url": getattr(page, "url", ""),
                    }))
                except Exception as action_err:
                    await websocket.send_text(json.dumps({
                        "type": "action_result",
                        "status": "error",
                        "kind": kind,
                        "message": str(action_err),
                    }))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("[BrowserRoutes] Stream error: %s", e)
    finally:
        stop_event.set()
        sender_task.cancel()
        if fallback_task:
            fallback_task.cancel()
        if cdp and screencast_active:
            try:
                await cdp.send("Page.stopScreencast")
            except Exception:
                pass
            try:
                await cdp.detach()
            except Exception:
                pass
