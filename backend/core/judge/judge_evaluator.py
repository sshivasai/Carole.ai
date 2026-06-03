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

from core.chat.event_bus import event_bus
from core.llm.multi_model_router import llm_router
from core.config import JUDGE_SYSTEM_PROMPT, DEFAULT_FAST_MODEL

class JudgeEvaluator:
    async def evaluate(self, tool_name: str, arguments: dict, agent_name: str) -> bool:
        """
        Calls a cheap LLM to assess whether a tool execution request is safe.
        Returns True if approved, False if denied.
        """
        prompt = (
            f"Agent '{agent_name}' wants to execute tool '{tool_name}' "
            f"with arguments: {arguments}\n\n"
            f"Should this be APPROVED or DENIED?"
        )

        response = await llm_router.generate_completion(
            model=DEFAULT_FAST_MODEL,
            system_prompt=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )

        verdict = response.strip().upper()
        approved = "APPROVE" in verdict
        print(f"⚖️ [Judge] Tool '{tool_name}' by '{agent_name}' → {'APPROVED' if approved else 'DENIED'}")
        return approved


# Singleton
judge_evaluator = JudgeEvaluator()
