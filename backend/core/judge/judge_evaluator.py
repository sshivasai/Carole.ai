"""
# backend/core/judge/judge_evaluator.py

Passive Judge AI that evaluates tool execution requests on the EventBus.

When a tool is gated at "judge" level, the ToolExecutor publishes a
`judge_review_request` event. This evaluator:
1. Subscribes to team topics.
2. Receives review requests.
3. Calls a cheap LLM to assess risk.
4. Publishes an approval or denial result.
"""

from core.llm.multi_model_router import llm_router
from core.config import JUDGE_SYSTEM_PROMPT, DEFAULT_JUDGE_MODEL
import re

class JudgeEvaluator:
    async def evaluate(self, tool_name: str, arguments: dict, agent_name: str, team_id: str = None) -> tuple[bool, str]:
        """
        Calls a cheap LLM to assess whether a tool execution request is safe.
        Returns (approved: bool, reasoning: str).
        """
        history_text = ""
        if team_id:
            try:
                import uuid
                from core.memory.database import async_session
                from core.memory.models import Message
                from sqlalchemy import select

                team_uuid = uuid.UUID(team_id) if isinstance(team_id, str) else team_id
                async with async_session() as db_session:
                    stmt = (
                        select(Message)
                        .where(Message.team_id == team_uuid)
                        .order_by(Message.created_at.desc())
                        .limit(10)
                    )
                    result = await db_session.execute(stmt)
                    messages = list(reversed(result.scalars().all()))
                    if messages:
                        history_text = "Recent Chat Context:\n"
                        for msg in messages:
                            sender = msg.sender_name or msg.sender_id
                            history_text += f"[{sender}]: {msg.text}\n"
                        history_text += "\n"
            except Exception as e:
                print(f"Error loading chat context for judge: {e}")

        prompt = (
            f"Agent '{agent_name}' wants to execute tool '{tool_name}' "
            f"with arguments: {arguments}\n\n"
            f"{history_text}"
            f"Please analyze the safety of this request. Provide your reasoning inside <REASONING> tags.\n"
            f"Then, conclude with exactly <VERDICT>APPROVED</VERDICT> or <VERDICT>DENIED</VERDICT>."
        )

        response = await llm_router.generate_completion(
            model=DEFAULT_JUDGE_MODEL,
            system_prompt=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=300,
        )

        reasoning = ""
        r_match = re.search(r"<REASONING>(.*?)</REASONING>", response, re.DOTALL | re.IGNORECASE)
        if r_match:
            reasoning = r_match.group(1).strip()
        else:
            reason = re.sub(r"<VERDICT>.*?</VERDICT>", "", response, flags=re.IGNORECASE).strip()
            reasoning = reason if reason else "No explanation provided by the Judge."

        verdict_text = response.upper()
        approved = "APPROVE" in verdict_text
        print(f"[Judge] Tool '{tool_name}' by '{agent_name}' -> {'APPROVED' if approved else 'DENIED'}")
        if not reasoning:
            print(f"[Judge] WARNING: Empty reasoning. Raw response: {response}")
        
        return approved, reasoning


# Singleton
judge_evaluator = JudgeEvaluator()
