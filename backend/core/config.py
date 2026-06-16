"""
# backend/core/config.py

Centralized configuration for Carole.ai.
Runtime settings (models, loops, timeouts) live here.
All prompt text has been moved to:
  backend/core/defaults/prompts.json        (shipped defaults)
  ~/.carole/prompts.json                    (user overrides — edit via Settings UI)
"""

import os
from pathlib import Path

# ==========================================
# Global Application Data Directory
# ==========================================
CAROLE_HOME_DIR = Path.home() / ".carole"
CAROLE_HOME_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# Global Model Settings  (env-configurable)
# ==========================================
DEFAULT_FAST_MODEL  = os.getenv("DEFAULT_FAST_MODEL",  "openrouter/free")
DEFAULT_SMART_MODEL = os.getenv("DEFAULT_SMART_MODEL", "openrouter/free")
DEFAULT_CODER_MODEL = os.getenv("DEFAULT_CODER_MODEL", "openrouter/free")
DEFAULT_JUDGE_MODEL = os.getenv("DEFAULT_JUDGE_MODEL", "openrouter/free")

# ==========================================
# Agent Runtime Settings (env-configurable)
# ==========================================
MAX_LOOPS            = int(os.getenv("MAX_AGENT_LOOPS",       "10"))
APPROVAL_TIMEOUT_SECS = int(os.getenv("APPROVAL_TIMEOUT_SECS", "300"))
MAX_QUEUE_SIZE       = int(os.getenv("MAX_EVENT_QUEUE_SIZE",  "500"))

# ==========================================
# Memory & Dream Settings
# ==========================================
DREAM_INTERVAL_MINUTES        = 15
MEMORY_RETRIEVAL_LIMIT        = 3
CONTEXT_COMPACTION_THRESHOLD  = 15   # messages before compaction triggers


# ==========================================
# Prompt shims — backward-compatible aliases
# All text is now stored in prompts.json.
# Use get_prompt() directly in new code.
# ==========================================

def _p(slug: str, **kw) -> str:
    """Lazy import to avoid circular imports at module load time."""
    from core.prompts import get_prompt
    return get_prompt(slug, **kw)


# These module-level constants are kept for backward compatibility.
# They are evaluated lazily (function call) rather than at import time.

def _lazy(slug: str):
    """Returns a property-like callable that re-reads the prompt on every access."""
    from core.prompts import get_prompt
    return get_prompt(slug)


# Backward-compatible module attributes — evaluated on first access via __getattr__
_PROMPT_ALIASES = {
    "CONSOLIDATION_PROMPT":     "system.consolidation",
    "JUDGE_SYSTEM_PROMPT":      "system.judge",
    "STRICT_REASONING_GUIDELINES": "system.tool_use",
    "COORDINATOR_DIRECTIVES":   "system.coordinator_directives",
    "COMPACTION_SYSTEM_PROMPT": "system.compaction_system",
    "COMPACTION_USER_PROMPT":   "system.compaction_user",
    "KEYWORD_EXTRACTION_PROMPT":"system.keyword_extraction",
}


def __getattr__(name: str) -> str:
    """
    Module-level __getattr__ so old-style `from core.config import JUDGE_SYSTEM_PROMPT`
    still works — it now reads from prompts.json instead of a hardcoded string.
    """
    if name in _PROMPT_ALIASES:
        from core.prompts import get_prompt
        return get_prompt(_PROMPT_ALIASES[name])
    raise AttributeError(f"module 'core.config' has no attribute {name!r}")


