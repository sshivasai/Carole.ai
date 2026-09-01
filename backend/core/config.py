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

PLUGINS_DIR = CAROLE_HOME_DIR / "plugins"
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

DISABLED_GLOBAL_MCPS_FILE = CAROLE_HOME_DIR / "disabled_global_mcps.json"

GLOBAL_MCPS = [
    {
        "server_name": "context7",
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp@latest"],
        "description": "Live library and framework documentation"
    },
    {
        "server_name": "markitdown",
        "command": "uvx",
        "args": ["markitdown-mcp"],
        "description": "Convert PDF/Word/Excel/Images to Markdown"
    },
    {
        "server_name": "sequential_thinking",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
        "description": "Structured step-by-step reasoning scaffold"
    }
]

# ==========================================
# Global Model Settings  (env-configurable)
# ==========================================
# Values are now dynamically loaded from __getattr__ so they update without restart

# ==========================================
# Agent Runtime Settings (env-configurable)
# ==========================================
# Values are now dynamically loaded from __getattr__ so they update without restart

# ==========================================
# Memory & Dream Settings
# ==========================================
# Values are now dynamically loaded from __getattr__ so they update without restart


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
    "OUTPUT_EFFICIENCY_PROMPT": "system.output_efficiency",
}


_MODEL_DEFAULTS = {
    "DEFAULT_FAST_MODEL": "openrouter/free",
    "DEFAULT_SMART_MODEL": "openrouter/free",
    "DEFAULT_CODER_MODEL": "openrouter/free",
    "DEFAULT_JUDGE_MODEL": "openrouter/free",
}

_AGENT_SETTINGS_DEFAULTS = {
    "MAX_LOOPS": 25,
    "APPROVAL_TIMEOUT_SECS": 60,
    "MAX_QUEUE_SIZE": 500,
    "DREAM_INTERVAL_MINUTES": 15,
    "MEMORY_RETRIEVAL_LIMIT": 5,
    "CONTEXT_COMPACTION_THRESHOLD": 15,
}

def __getattr__(name: str):
    """
    Module-level __getattr__ so old-style `from core.config import JUDGE_SYSTEM_PROMPT`
    still works — it now reads from prompts.json instead of a hardcoded string.
    """
    if name in _PROMPT_ALIASES:
        from core.prompts import get_prompt
        return get_prompt(_PROMPT_ALIASES[name])
    
    if name in _MODEL_DEFAULTS:
        from core.llm.config_manager import load_config
        cfg = load_config()
        # 1. Check user config file (~/.carole/config.json)
        from_cfg = cfg.get("default_models", {}).get(name)
        if from_cfg:
            return from_cfg
        # 2. Check environment variable
        from_env = os.getenv(name)
        if from_env:
            return from_env
        # 3. Fallback
        return _MODEL_DEFAULTS[name]

    if name in _AGENT_SETTINGS_DEFAULTS:
        from core.llm.config_manager import load_config
        cfg = load_config()
        # 1. Check user config file
        from_cfg = cfg.get("agent_settings", {}).get(name)
        if from_cfg is not None:
            return int(from_cfg)
        # 2. Check env variables (for some)
        env_map = {
            "MAX_LOOPS": "MAX_AGENT_LOOPS",
            "APPROVAL_TIMEOUT_SECS": "APPROVAL_TIMEOUT_SECS",
            "MAX_QUEUE_SIZE": "MAX_EVENT_QUEUE_SIZE"
        }
        if name in env_map:
            from_env = os.getenv(env_map[name])
            if from_env is not None:
                return int(from_env)
        # 3. Fallback
        return int(_AGENT_SETTINGS_DEFAULTS[name])

    raise AttributeError(f"module 'core.config' has no attribute {name!r}")


