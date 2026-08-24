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
from typing import Dict, List, Optional

from core.chat.event_bus import event_bus
from core.config import APPROVAL_TIMEOUT_SECS

logger = logging.getLogger("carole.interaction_tools")

# Pending questions: maps question_id -> asyncio.Event
pending_questions: Dict[str, asyncio.Event] = {}
# Answers: maps question_id -> answer text
question_answers: Dict[str, str] = {}


class InteractionTools:
    async def ask_user(
        self, question: str, agent_id: str, agent_name: str, team_id: str,
        options: Optional[List[str]] = None
    ) -> str:
        """
        Sends a question to the human and blocks until they reply.

        Args:
            question: The question text to display.
            agent_id: UUID of the agent asking.
            agent_name: Display name of the agent.
            team_id: Team context for event routing.
            options: Optional list of choice strings for multiple-choice UI.
                     If provided, the frontend renders a clickable option card.
                     The human may still type a free-form answer.

        The reply comes in via the WebSocket as a message with the question_id.
        Times out after APPROVAL_TIMEOUT_SECS to prevent indefinite blocking.
        """
        q_id = str(uuid.uuid4())
        event = asyncio.Event()
        pending_questions[q_id] = event

        payload = {
            "type": "agent_question",
            "question_id": q_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "question": question,
            "text": f"❓ {agent_name} asks: {question}",
        }
        if options:
            payload["options"] = [str(o) for o in options]

        await event_bus.publish(f"team:{team_id}", payload)

        logger.info(
            "❓ [InteractionTools] Agent '%s' asked: %.80s (q_id=%s, options=%s)",
            agent_name, question, q_id[:8], options
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

        answer = question_answers.pop(q_id, "")
        logger.info("[InteractionTools] q_id=%s answered: %.80s", q_id[:8], answer)
        return f"Human answered: {answer}"

    async def sleep(self, seconds: float) -> str:
        """Pauses execution for the given number of seconds (max 60)."""
        seconds = min(seconds, 60.0)
        await asyncio.sleep(seconds)
        return f"Slept for {seconds} seconds."


# Singleton
interaction_tools = InteractionTools()
