"""
# backend/core/tools/browser_agent.py

Autonomous browser agent. Turns a single natural-language command into a
complete, self-directed browsing session.

Design:
  - Reuses the shared Playwright pool (browser_pool) and the BrowserTool
    snapshot/ref primitives, so it inherits stealth, CAPTCHA handling, dialog
    handling, and screenshot streaming for free.
  - Runs a tight inner ReACT loop: snapshot → LLM decision (JSON) → act → observe.
  - The LLM sees a numbered Accessibility Tree (Refs) and picks the next action.
  - Detects completion (done=true), stuck loops, and hard failures.
  - Returns a structured summary the calling agent can relay to the user.

Exposed to agents as the `browser_task` tool, so a user can say
"go book the cheapest flight to NYC" and the agent handles every navigation,
form fill, and click on its own.
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("carole.browser_agent")

MAX_STEPS = 20
SNAPSHOT_MAX_CHARS = 14_000
HISTORY_KEEP = 6  # how many recent (decision, observation) turns to feed back
STUCK_THRESHOLD = 3  # identical snapshots in a row before giving up

BROWSER_AGENT_SYSTEM_PROMPT = """You are an autonomous web-browsing agent. You are given a GOAL and the current state of a real Chromium browser as a numbered Accessibility Tree. Every interactive element has a number in brackets, e.g. [12].

Your job is to complete the GOAL by deciding the next single action, one step at a time. You do NOT see the raw page — only the numbered tree, the current URL, and your recent action history.

Respond with EXACTLY ONE JSON object and nothing else, in one of these two shapes:

To take an action:
{"thought": "<brief reason>", "done": false, "action": {"type": "<type>", ...}}

To finish (only when the GOAL is actually complete or genuinely impossible):
{"thought": "<why>", "done": true, "success": true, "summary": "<concise result for the user>"}

Available action types (ref refers to a bracketed number from the CURRENT snapshot):
- navigate   : {"type": "navigate", "url": "https://..."}  — go to a URL
- click      : {"type": "click", "ref": 12}                 — click element
- type       : {"type": "type", "ref": 12, "text": "hello"} — type into input
- clear      : {"type": "clear", "ref": 12}                 — clear an input
- hover      : {"type": "hover", "ref": 12}                 — hover
- select     : {"type": "select", "ref": 12, "value": "NYC"}— pick a <select> option
- check      : {"type": "check", "ref": 12}                 — check a checkbox
- uncheck    : {"type": "uncheck", "ref": 12}               — uncheck a checkbox
- press      : {"type": "press", "key": "Enter"}            — press a key
- scroll_down: {"type": "scroll_down"}                      — scroll page down
- scroll_up  : {"type": "scroll_up"}                        — scroll page up
- go_back    : {"type": "go_back"}                          — browser back
- wait       : {"type": "wait", "ms": 2000}                 — wait for async content
- browser_human_takeover : {"type": "browser_human_takeover", "reason": "Please solve the Cloudflare CAPTCHA / 2FA / Login on screen"} — request human takeover

Rules:
1. Ref numbers change after every navigation or DOM update. Always act on the LATEST snapshot's numbers — never reuse a stale ref.
2. If a form has multiple fields, fill them one at a time, then click the submit button.
3. If you are on a search page, find the search input, type the query, then press Enter or click the search button.
4. If a page is loading or content is missing, use wait or scroll_down before giving up.
5. If the same action fails twice, try a different approach (scroll to reveal, re-navigate, or use a different element).
6. Only set done=true when the goal is truly finished (you have the answer / completed the action). If you cannot complete it, set done=true with success=false and a clear explanation.
7. Prefer the most specific, visible element. Ignore hidden/duplicate refs.
8. If you encounter a CAPTCHA (Cloudflare, reCAPTCHA), 2FA/OTP prompt, OAuth SSO login (Google/GitHub), or a stuck blocking modal you cannot bypass, call `browser_human_takeover` with a clear reason for the user.
9. Checkboxes & Radios: If an input element has `checked='false'`, it is currently unchecked. If the goal requires selecting/agreeing to terms or opting in, you MUST use action `{"type": "check", "ref": <ref>}` to check it before submitting the form. Never assume a checkbox is checked unless `checked='true'` is explicitly shown.
10. Dropdowns & Selects: For <select> elements, do NOT use 'click' to open them (headless browsers cannot open native OS dropdown menus). You MUST directly use the 'select' action: {"type": "select", "ref": <ref>, "value": "<option_value_or_label>"}. The available options are listed directly on the <select> tag in the snapshot.
"""


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Pull the first valid JSON object out of an LLM response."""
    if not text:
        return None
    text = text.strip()

    def _try_parse(s: str) -> Optional[Dict[str, Any]]:
        s = s.strip()
        # 1. Direct JSON
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # 2. Strip trailing commas before closing braces/brackets
        try:
            cleaned = re.sub(r",\s*([\]}])", r"\1", s)
            obj = json.loads(cleaned)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # 3. Clean control characters / fix newlines in strings via ReACTAgent
        try:
            from core.agent.react_agent import ReACTAgent
            repaired = ReACTAgent._repair_json(s)
            obj = json.loads(repaired)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # 4. AST literal_eval fallback (handles single quotes, True/False/None)
        try:
            import ast
            obj = ast.literal_eval(s)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        return None

    # Step A: Check code blocks (```json ... ``` or ``` ... ```)
    fences = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
    for fence in fences:
        parsed = _try_parse(fence)
        if parsed:
            return parsed

    # Step B: Scan all balanced top-level { ... } blocks in the text
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break

        depth = 0
        in_str = False
        esc = False
        end = -1
        for j in range(start, len(text)):
            c = text[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end = j
                        break
        if end != -1:
            candidate = text[start : end + 1]
            parsed = _try_parse(candidate)
            if parsed and any(k in parsed for k in ("thought", "action", "done", "type", "success")):
                return parsed
            i = start + 1
        else:
            break

    # Step C: Fallback to _try_parse on whole text
    return _try_parse(text)


class BrowserAgent:
    """A self-directed loop that completes a browsing command end-to-end."""

    def __init__(self, model: str):
        self.model = model

    async def run(
        self,
        command: str,
        agent_id: str,
        agent_name: str,
        team_id: str,
        start_url: Optional[str] = None,
    ) -> str:
        from core.tools.browser_pool import get_page
        from core.tools.browser_tool import browser_tool
        from core.llm.multi_model_router import llm_router

        page = await get_page(agent_id)

        # Optionally seed the session with a starting URL.
        if start_url:
            try:
                await browser_tool.navigate(start_url, agent_id, agent_name, team_id)
            except Exception as e:
                logger.warning("browser_task: initial navigate failed: %s", e)

        messages: List[Dict[str, str]] = []
        last_snapshot = ""
        stuck_count = 0

        # ── Inner ReACT loop ────────────────────────────────────────────────
        for step in range(1, MAX_STEPS + 1):
            snapshot = await self._snapshot(page, browser_tool)
            url = page.url

            if snapshot == last_snapshot:
                stuck_count += 1
                if stuck_count >= STUCK_THRESHOLD:
                    return self._finalize(
                        "⚠️ Browsing stopped: the page stopped changing after "
                        f"{stuck_count} steps (possible infinite loop, popup, or "
                        "infinite-scroll page). Try a more specific command."
                    )
            else:
                stuck_count = 0
            last_snapshot = snapshot

            state_block = self._build_state_block(url, snapshot, step)

            if not messages:
                messages.append({
                    "role": "user",
                    "content": f"GOAL: {command}\n\n{state_block}",
                })
            else:
                messages.append({"role": "user", "content": state_block})

            # Keep the context bounded: drop old turns but always retain the goal.
            messages = self._trim_history(messages)

            decision = None
            for attempt in range(2):
                try:
                    raw = await llm_router.generate_completion(
                        model=self.model,
                        system_prompt=BROWSER_AGENT_SYSTEM_PROMPT,
                        messages=messages,
                        temperature=0.2,
                        max_tokens=1200,
                        team_id=team_id,
                        agent_id=agent_id,
                        agent_name=agent_name,
                    )
                    decision = _extract_json(raw)
                    if decision is not None:
                        logger.info("🤖 [BrowserAgent] Step %d decision: %s", step, decision)
                        break
                    logger.warning("🤖 [BrowserAgent] Step %d attempt %d failed to parse JSON from raw: %r", step, attempt, raw)
                    # Retry once with a nudge if JSON parsing failed.
                    messages.append({
                        "role": "user",
                        "content": "Your previous response was not valid JSON. "
                                   "Reply with exactly one JSON object.",
                    })
                except Exception as e:
                    logger.warning("browser_task: LLM error (step %d): %s", step, e)
                    if attempt == 1:
                        return self._finalize(f"⚠️ Browsing failed: LLM error — {e}")

            if decision is None:
                return self._finalize(
                    "⚠️ Browsing failed: could not parse the model's decision as JSON."
                )

            # Record the decision as an assistant turn.
            messages.append({"role": "assistant", "content": json.dumps(decision)})

            # Terminal signal.
            if decision.get("done"):
                success = bool(decision.get("success", True))
                summary = decision.get("summary") or decision.get("thought") or "Task completed."
                prefix = "✓" if success else "✗"
                return self._finalize(f"{prefix} {summary.strip()}")

            # Execute the action.
            action = decision.get("action") or {}
            result = await self._execute_action(
                browser_tool, page, action, agent_id, agent_name, team_id
            )
            messages.append({"role": "user", "content": f"RESULT: {result}"})

        return self._finalize(
            f"⚠️ Browsing stopped after {MAX_STEPS} steps without completing the goal. "
            "Try a more specific command or a direct URL."
        )

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _snapshot(self, page, browser_tool) -> str:
        try:
            text = await browser_tool._build_snapshot_text(page)
            if text.startswith("Error"):
                return "(snapshot unavailable)"
            return text[:SNAPSHOT_MAX_CHARS]
        except Exception as e:
            logger.warning("browser_task: snapshot error: %s", e)
            return "(snapshot unavailable)"

    def _build_state_block(self, url: str, snapshot: str, step: int) -> str:
        return (
            f"STEP {step}\n"
            f"CURRENT URL: {url}\n"
            f"PAGE SNAPSHOT (numbered refs — act only on these):\n{snapshot}"
        )

    def _trim_history(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        # Keep the first (goal) message plus the last HISTORY_KEEP turns.
        if len(messages) <= 1 + HISTORY_KEEP * 2:
            return messages
        head = messages[:1]
        tail = messages[-(HISTORY_KEEP * 2):]
        return head + tail

    async def _execute_action(
        self, browser_tool, page, action: Dict[str, Any],
        agent_id: str, agent_name: str, team_id: str,
    ) -> str:
        kind = (action.get("type") or "").strip()
        try:
            if kind == "navigate":
                url = action.get("url") or action.get("value")
                if not url:
                    return "Error: navigate requires a 'url'."
                return await browser_tool.navigate(url, agent_id, agent_name, team_id)
            if kind == "go_back":
                return await browser_tool.go_back(agent_id, agent_name, team_id)
            if kind == "wait":
                ms = int(action.get("ms", 1000))
                return await browser_tool.wait_ms(ms, agent_id)
            if kind == "press":
                key = action.get("key")
                if not key:
                    return "Error: press requires a 'key'."
                return await browser_tool.act("press", agent_id, agent_name, team_id, key=key)
            if kind in ("scroll_down", "scroll_up"):
                return await browser_tool.act(kind, agent_id, agent_name, team_id)
            if kind in ("click", "type", "clear", "hover", "select", "check", "uncheck"):
                raw_ref = action.get("ref")
                ref = None
                if raw_ref is not None:
                    cleaned_ref = str(raw_ref).strip("[] \t\r\n")
                    ref = int(cleaned_ref) if cleaned_ref.isdigit() else cleaned_ref
                return await browser_tool.act(
                    kind,
                    agent_id,
                    agent_name,
                    team_id,
                    ref=ref,
                    text=action.get("text"),
                    value=action.get("value"),
                )
            if kind in ("browser_human_takeover", "ask_human"):
                from core.tools.interaction_tools import interaction_tools
                reason = action.get("reason") or "Manual user intervention required in the browser."
                captcha_img = None
                try:
                    import base64
                    shot_bytes = await page.screenshot(type="jpeg", quality=65)
                    captcha_img = base64.b64encode(shot_bytes).decode("utf-8")
                except Exception as shot_err:
                    logger.debug("Takeover screenshot capture failed: %s", shot_err)

                return await interaction_tools.browser_human_takeover(
                    reason=reason,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    team_id=team_id,
                    captcha_image_base64=captcha_img,
                )
            return f"Error: unknown action type '{kind}'."
        except Exception as e:
            logger.warning("browser_task: action %s failed: %s", kind, e)
            return f"Error: {kind} failed — {e}"

    @staticmethod
    def _finalize(message: str) -> str:
        return message
