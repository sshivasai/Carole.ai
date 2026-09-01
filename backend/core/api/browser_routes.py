"""
# backend/core/api/browser_routes.py

API routes for real-time interactive browser takeover (Solution 2)
and direct canvas click/key forwarding.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any
import base64
import logging

from core.auth.auth_middleware import require_auth
from core.tools.browser_tool import browser_tool, _get_page, _publish_screenshot
from core.tools.interaction_tools import pending_questions, question_answers

logger = logging.getLogger("carole.browser_routes")

router = APIRouter(prefix="/api/browser", tags=["browser"])


class BrowserActRequest(BaseModel):
    agent_id: Optional[str] = "global"
    kind: str  # click, coords, type, press, scroll_down, scroll_up, navigate
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
    Direct interactive browser action dispatcher for frontend Canvas takeover (Solution 2).
    Forwards user clicks, keypresses, typing, and navigation to the live Playwright page.
    """
    try:
        page = await _get_page(body.agent_id or "global")
        kind = body.kind.lower()

        if kind == "coords" and body.x is not None and body.y is not None:
            # Click at exact normalized viewport coordinates
            await page.mouse.click(body.x, body.y)
        elif kind == "click" and body.selector:
            await page.click(body.selector, timeout=5000)
        elif kind == "type" and body.text:
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
        elif kind == "navigate" and body.url:
            from core.tools.ssrf_guard import assert_safe_public_url
            safe_url = assert_safe_public_url(body.url, allow_local=True)
            await page.goto(safe_url, wait_until="domcontentloaded", timeout=20000)
        else:
            return {"status": "error", "message": f"Unsupported or incomplete action '{kind}'."}

        # Small delay for rendering
        import asyncio
        await asyncio.sleep(0.3)

        # Capture updated screenshot
        screenshot_bytes = await page.screenshot(type="jpeg", quality=60)
        b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        return {
            "status": "success",
            "url": page.url,
            "title": await page.title(),
            "screenshot": f"data:image/jpeg;base64,{b64}",
        }
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
    try:
        page = await _get_page(agent_id)
        screenshot_bytes = await page.screenshot(type="jpeg", quality=60)
        b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        return {
            "status": "success",
            "url": page.url,
            "title": await page.title(),
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
    if q_id in pending_questions:
        question_answers[q_id] = body.answer
        pending_questions[q_id].set()
        return {"status": "success", "message": "Intervention marked as resolved."}
    return {"status": "not_found", "message": "Question event has already completed or expired."}
