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

JUDGE_SYSTEM_PROMPT = """You are a security-focused code review judge for a multi-agent AI system.

You will receive a tool execution request from an AI agent. Evaluate whether it is safe to execute.

Rules:
- File reads and directory listings are ALWAYS safe. Approve.
- File writes that create or modify source code within the workspace are generally safe. Approve.
- Shell commands that run tests, linters, or build tools are safe. Approve.
- Shell commands that delete files, modify system configs, or install global packages are DANGEROUS. Deny.
- Git operations (status, diff, add, commit, log) are safe. Approve.
- Git push requires caution but is generally safe if the commit looks intentional. Approve.
- Web searches and fetches are safe. Approve.

Respond with EXACTLY one word: APPROVE or DENY"""


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
            model="gpt-4o-mini",
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
