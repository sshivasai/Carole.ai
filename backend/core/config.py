"""
# backend/core/config.py

Centralized configuration for Carole.ai.
Contains default models, prompts, memory settings, and system guidelines.
Users can edit this file or set environment variables to control behaviour.

Environment Variables (all optional):
  DEFAULT_FAST_MODEL   — lightweight model for cheap/frequent calls (default: openrouter/free)
  DEFAULT_SMART_MODEL  — high-capability model for complex reasoning (default: openrouter/free)
  DEFAULT_CODER_MODEL  — code-optimised model (default: openrouter/free)
"""

import os

# ==========================================
# Global Model Settings  (env-configurable)
# ==========================================
DEFAULT_FAST_MODEL  = os.getenv("DEFAULT_FAST_MODEL",  "openrouter/free")
DEFAULT_SMART_MODEL = os.getenv("DEFAULT_SMART_MODEL", "openrouter/free")
DEFAULT_CODER_MODEL = os.getenv("DEFAULT_CODER_MODEL", "openrouter/free")

# ==========================================
# Memory & Dream Settings
# ==========================================
DREAM_INTERVAL_MINUTES = 15
MEMORY_RETRIEVAL_LIMIT = 3
CONTEXT_COMPACTION_THRESHOLD = 15  # Number of messages before compaction is triggered

CONSOLIDATION_PROMPT = """You are a knowledge extraction engine. Analyze the following conversation log from a multi-agent team chat.

Extract the most important lessons learned, decisions made, or mistakes to avoid.
For EACH lesson, output it in this exact format (one per line):

TASK_SUMMARY: <brief context of what was being discussed or done>
LESSON_RULE: <concrete, actionable rule to follow or mistake to avoid in the future>

Only extract genuinely useful lessons. If the conversation is casual or contains no actionable knowledge, output: NO_LESSONS

Conversation log:
{conversation}"""

# ==========================================
# Judge AI Settings
# ==========================================
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

# ==========================================
# Agent Prompting Guidelines
# ==========================================
STRICT_REASONING_GUIDELINES = """
<strict-reasoning-guidelines>
1. CONFIDENCE ASSESSMENT: If your internal data is old or missing, call `web_search` or `web_fetch` first.
2. WEB CITATIONS: When using web data, include source URLs in your response.
3. TOOL CALLS: Use [ACTION]tool_name({"param": "value"})[/ACTION] to invoke tools.
4. NATURAL SPEECH: Talk like a real dev in a team chat. Be concise and direct.
5. When done, just say your final answer — no [ACTION] tag means you're finished.
</strict-reasoning-guidelines>
"""

COORDINATOR_DIRECTIVES = """
<coordinator-directives>
You are the COORDINATOR. Your job is to:
1. Break complex requests into concrete sub-tasks.
2. Assign tasks to the right teammate based on their role.
3. Use spawn_agent to kick off a worker, or send_message to continue one.
4. When workers finish, they send <task-notification> messages. Read them carefully.
5. NEVER delegate understanding. After a worker reports back, synthesize their findings.
6. Track progress with create_task / update_task tools.
7. When everything is done, summarize the results to the team.
</coordinator-directives>
"""

KEYWORD_EXTRACTION_PROMPT = (
    "Extract 3-5 highly specific technical keywords from this task for a search engine. "
    "Return ONLY the keywords separated by spaces. Task: {task}"
)

COMPACTION_SYSTEM_PROMPT = "You are a context compactor for an AI agent."
COMPACTION_USER_PROMPT = (
    "Summarize the following conversation and tool execution results concisely. "
    "Retain all critical facts, file paths, errors, and outcomes:\n{context}"
)
