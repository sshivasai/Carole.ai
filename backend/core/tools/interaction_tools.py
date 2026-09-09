"""
# backend/core/tools/interaction_tools.py

Tools for direct Agent-to-Human interaction during a ReACT loop.

- ask_user: Pauses the agent and sends a question to the human via EventBus.
            Blocks until the human replies via WebSocket.
            Times out after APPROVAL_TIMEOUT_SECS (default 300s) to prevent
            agents hanging forever if the human never responds.
- sleep: Pauses execution for a specified duration.

Race-condition fix (v2):
  pending_questions and question_answers are dicts, not WeakDicts — entries
  are cleaned up in ALL exit paths (answer received, timeout, exception) so
  the dicts don't grow unboundedly when agents disconnect mid-question.
"""

import asyncio
import uuid
import logging
from typing import Dict, List, Optional, Any

from core.chat.event_bus import event_bus
from core.config import APPROVAL_TIMEOUT_SECS

logger = logging.getLogger("carole.interaction_tools")

# Pending questions: maps question_id -> asyncio.Event
pending_questions: Dict[str, asyncio.Event] = {}
# Answers: maps question_id -> answer text
question_answers: Dict[str, str] = {}
# Question details: maps question_id -> metadata (team_id, agent_id)
pending_question_details: Dict[str, dict] = {}


class InteractionTools:
    async def ask_user(
        self, question: str, agent_id: str, agent_name: str, team_id: str,
        options: Optional[List[str]] = None,
        questions: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Sends question(s) to the human and blocks until they reply.

        Args:
            question: Single question text to display (legacy or primary).
            agent_id: UUID of the agent asking.
            agent_name: Display name of the agent.
            team_id: Team context for event routing.
            options: Optional list of choice strings for single-question multiple-choice UI.
            questions: Optional list of question dicts for batching multiple questions:
                       [{'id': 'q1', 'question': '...', 'options': ['A', 'B'], 'is_multi_select': False}]

        The reply comes in via the WebSocket as a message with the question_id.
        Times out after APPROVAL_TIMEOUT_SECS to prevent indefinite blocking.
        """
        q_id = str(uuid.uuid4())
        event = asyncio.Event()
        pending_questions[q_id] = event
        pending_question_details[q_id] = {"team_id": team_id, "agent_id": agent_id}

        display_text = question
        if questions and len(questions) > 1:
            q_list_summary = "; ".join(f"{i+1}. {q.get('question', '')}" for i, q in enumerate(questions))
            display_text = f"❓ {agent_name} asks {len(questions)} questions: {q_list_summary}"
        else:
            display_text = f"❓ {agent_name} asks: {question}"

        payload: Dict[str, Any] = {
            "type": "agent_question",
            "question_id": q_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "question": question or (questions[0].get("question", "") if questions else ""),
            "text": display_text,
        }
        if options:
            payload["options"] = [str(o) for o in options]
        if questions:
            payload["questions"] = questions

        await event_bus.publish(f"team:{team_id}", payload)

        logger.info(
            "❓ [InteractionTools] Agent '%s' asked: %.80s (q_id=%s, multi=%s)",
            agent_name, display_text, q_id[:8], bool(questions)
        )

        try:
            await asyncio.wait_for(event.wait(), timeout=float(APPROVAL_TIMEOUT_SECS))
        except asyncio.TimeoutError:
            # Clean up stale entries — prevents unbounded dict growth
            pending_questions.pop(q_id, None)
            question_answers.pop(q_id, None)
            logger.warning(
                "[InteractionTools] Question q_id=%s timed out after %ds — no answer received.",
                q_id[:8], APPROVAL_TIMEOUT_SECS
            )
            return f"No answer received — the human did not respond within {APPROVAL_TIMEOUT_SECS}s."
        finally:
            # Ensure cleanup in all exit paths (answer received or exception)
            pending_questions.pop(q_id, None)
            pending_question_details.pop(q_id, None)

        raw_answer = question_answers.pop(q_id, "")
        logger.info("[InteractionTools] q_id=%s answered: %.80s", q_id[:8], raw_answer)

        # Parse structured answer if JSON
        formatted_answer = raw_answer
        if raw_answer.strip().startswith("{") and raw_answer.strip().endswith("}"):
            try:
                import json
                parsed_ans = json.loads(raw_answer)
                if isinstance(parsed_ans, dict):
                    parts = []
                    for k, v in parsed_ans.items():
                        parts.append(f"- **{k}**: {v}")
                    formatted_answer = "\n".join(parts)
            except Exception:
                pass

        return f"Human answered:\n{formatted_answer}"

    async def browser_human_takeover(
        self,
        reason: str,
        agent_id: str,
        agent_name: str,
        team_id: str,
        timeout: Optional[float] = None,
        captcha_image_base64: Optional[str] = None,
    ) -> str:
        """
        Pauses autonomous browser execution and requests human takeover/intervention
        to solve a CAPTCHA, 2FA prompt, OAuth login, or manual roadblock.
        Blocks until the human completes the action and confirms in the UI or chat.
        """
        q_id = str(uuid.uuid4())
        event = asyncio.Event()
        pending_questions[q_id] = event
        pending_question_details[q_id] = {"team_id": team_id, "agent_id": agent_id}

        payload = {
            "type": "browser_intervention",
            "question_id": q_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "reason": reason,
            "text": f"🤖 {agent_name} needs browser takeover: {reason}",
            "captcha_image": captcha_image_base64,
        }

        await event_bus.publish(f"team:{team_id}", payload)

        wait_timeout = float(timeout) if timeout and timeout > 0 else float(APPROVAL_TIMEOUT_SECS)
        logger.info(
            "🌐 [BrowserHIL] Agent '%s' requested takeover: %.80s (q_id=%s, timeout=%ss)",
            agent_name, reason, q_id[:8], wait_timeout
        )

        try:
            await asyncio.wait_for(event.wait(), timeout=wait_timeout)
        except asyncio.TimeoutError:
            pending_questions.pop(q_id, None)
            pending_question_details.pop(q_id, None)
            question_answers.pop(q_id, None)
            logger.warning(
                "[BrowserHIL] Takeover q_id=%s timed out after %ds — no confirmation received.",
                q_id[:8], wait_timeout
            )
            return f"No human response received within {wait_timeout}s — browser takeover timed out."
        finally:
            pending_questions.pop(q_id, None)
            pending_question_details.pop(q_id, None)

        answer = question_answers.pop(q_id, "")
        logger.info("[BrowserHIL] q_id=%s resolved by human: %.80s", q_id[:8], answer or "Done")
        return f"Human completed intervention ({answer or 'Done'}). Browser state updated."

    async def sleep(self, seconds: float) -> str:
        """Pauses execution for the given number of seconds (max 60)."""
        seconds = min(seconds, 60.0)
        await asyncio.sleep(seconds)
        return f"Slept for {seconds} seconds."


# Singleton
interaction_tools = InteractionTools()
