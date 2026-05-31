"""
# backend/core/tools/interaction_tools.py

Tools for direct Agent-to-Human interaction during a ReACT loop.

- ask_user: Pauses the agent and sends a question to the human via EventBus.
            Blocks until the human replies via WebSocket.
- sleep: Pauses execution for a specified duration.
"""

import asyncio
import uuid
from typing import Dict, Any

from core.chat.event_bus import event_bus

# Pending questions: maps question_id -> asyncio.Event
pending_questions: Dict[str, asyncio.Event] = {}
# Answers: maps question_id -> answer text
question_answers: Dict[str, str] = {}


class InteractionTools:
    async def ask_user(self, question: str, agent_id: str, agent_name: str, team_id: str) -> str:
        """
        Sends a question to the human and blocks until they reply.
        The reply comes in via the WebSocket as a message with the question_id.
        """
        q_id = str(uuid.uuid4())
        event = asyncio.Event()
        pending_questions[q_id] = event

        await event_bus.publish(f"team:{team_id}", {
            "type": "agent_question",
            "question_id": q_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "question": question,
            "text": f"❓ {agent_name} asks: {question}",
        })

        print(f"❓ [InteractionTools] Agent '{agent_name}' asked: {question} (q_id={q_id[:8]})")

        # Block until human answers (timeout after 5 minutes)
        try:
            await asyncio.wait_for(event.wait(), timeout=300.0)
        except asyncio.TimeoutError:
            pending_questions.pop(q_id, None)
            return "No answer received — the human did not respond within 5 minutes."

        answer = question_answers.pop(q_id, "")
        pending_questions.pop(q_id, None)
        return f"Human answered: {answer}"

    async def sleep(self, seconds: float) -> str:
        """Pauses execution for the given number of seconds (max 60)."""
        seconds = min(seconds, 60.0)
        await asyncio.sleep(seconds)
        return f"Slept for {seconds} seconds."


# Singleton
interaction_tools = InteractionTools()
