"""
# backend/core/config.py

Centralized configuration for Carole.ai.
Runtime settings (models, loops, timeouts) live here.
All prompt text has been moved to:
  backend/core/defaults/prompts.json        (shipped defaults)
  ~/.carole/prompts.json                    (user overrides — edit via Settings UI)
"""

import os
import re
from pathlib import Path

# ==========================================
# Global Application Data Directory
# ==========================================
CAROLE_HOME_DIR = Path(os.environ.get("CAROLE_HOME_DIR", str(Path.home() / ".carole"))).expanduser().resolve()
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
    "ORCHESTRATOR_DIRECTIVES":  "system.coordinator_directives",
    "COMPACTION_SYSTEM_PROMPT": "system.compaction_system",
    "COMPACTION_USER_PROMPT":   "system.compaction_user",
    "KEYWORD_EXTRACTION_PROMPT":"system.keyword_extraction",
    "OUTPUT_EFFICIENCY_PROMPT": "system.output_efficiency",
    "BROWSER_AGENT_SYSTEM_PROMPT": "system.browser_agent",
}


_MODEL_DEFAULTS = {
    "DEFAULT_FAST_MODEL": "openrouter/free",
    "DEFAULT_SMART_MODEL": "openrouter/auto",
    "DEFAULT_CODER_MODEL": "openrouter/free",
    "DEFAULT_JUDGE_MODEL": "openrouter/free",
    "DEFAULT_EMBEDDING_MODEL": "auto",
}

_AGENT_SETTINGS_DEFAULTS = {
    "MAX_LOOPS": 25,
    "APPROVAL_TIMEOUT_SECS": 60,
    "MAX_QUEUE_SIZE": 500,
    "DREAM_INTERVAL_MINUTES": 15,
    "MEMORY_RETRIEVAL_LIMIT": 5,
    "CONTEXT_COMPACTION_THRESHOLD": 15,
    "MAX_BUDGET_TOKENS": int(os.environ.get("MAX_BUDGET_TOKENS", "1000000")),
}


_GOOGLE_FLASH_FALLBACK = "gemini-3.6-flash"


def _available_google_model_ids() -> set[str]:
    """Read the hot-reloaded Google catalog without importing it eagerly."""
    try:
        from core.llm.model_catalog import load_model_catalog

        provider = load_model_catalog().get("google", {})
        return {
            entry["value"].strip()
            for entry in provider.get("models", [])
            if isinstance(entry, dict)
            and isinstance(entry.get("value"), str)
            and entry["value"].strip()
        }
    except Exception:
        return set()


def _select_google_default_model() -> str:
    """Keep the pinned Flash model while available, then use a discovered stable Flash."""
    available = _available_google_model_ids()
    if not available or _GOOGLE_FLASH_FALLBACK in available:
        return _GOOGLE_FLASH_FALLBACK

    stable_flash: list[tuple[tuple[int, int], str]] = []
    for model in available:
        match = re.fullmatch(r"gemini-(\d+)\.(\d+)-flash", model)
        if match:
            stable_flash.append(((int(match.group(1)), int(match.group(2))), model))

    if stable_flash:
        return max(stable_flash)[1]
    return _GOOGLE_FLASH_FALLBACK


def _get_default_model(key: str, cfg: dict | None = None) -> str:
    from core.llm.config_manager import load_config, get_key

    cfg = cfg or load_config()

    # 1. Check user-configured default models in config.json
    configured = cfg.get("default_models", {}).get(key)
    if configured and isinstance(configured, str) and configured.strip():
        return configured.strip()

    # 2. Resolve active API keys (respecting config isolation: no host env leak if cfg has keys)
    google_key = get_key(cfg, "google", "GOOGLE_API_KEY")
    openai_key = get_key(cfg, "openai", "OPENAI_API_KEY")
    anthropic_key = get_key(cfg, "anthropic", "ANTHROPIC_API_KEY")
    openrouter_key = get_key(cfg, "openrouter", "OPENROUTER_API_KEY")

    if key == "DEFAULT_CODER_MODEL":
        if anthropic_key:
            return "claude-3-5-sonnet-latest"
        if openai_key:
            return "openai/gpt-4o"
        if google_key:
            return _select_google_default_model()
        if openrouter_key:
            return "openrouter/free"
        return _MODEL_DEFAULTS.get("DEFAULT_CODER_MODEL", "openrouter/free")

    elif key in ("DEFAULT_FAST_MODEL", "DEFAULT_JUDGE_MODEL"):
        if google_key:
            return _select_google_default_model()
        if openai_key:
            return "openai/gpt-4o-mini"
        if anthropic_key:
            return "claude-3-5-haiku-latest"
        if openrouter_key:
            return "openrouter/free"
        return _MODEL_DEFAULTS.get(key, "openrouter/free")

    elif key == "DEFAULT_EMBEDDING_MODEL":
        if openai_key:
            return "openai/text-embedding-3-small"
        if google_key:
            return "models/text-embedding-004"
        return _MODEL_DEFAULTS.get("DEFAULT_EMBEDDING_MODEL", "auto")

    else:  # DEFAULT_SMART_MODEL
        if openai_key:
            return "openai/gpt-4o"
        if anthropic_key:
            return "claude-3-5-sonnet-latest"
        if google_key:
            return _select_google_default_model()
        if openrouter_key:
            return "openrouter/auto"
        return _MODEL_DEFAULTS.get("DEFAULT_SMART_MODEL", "openrouter/auto")


def __getattr__(name: str):
    """
    Module-level __getattr__ so settings are dynamically resolved on every access:
    - User config (~/.carole/config.json) always takes precedence.
    - Host environment variables are only used as fallback if no keys exist in cfg.
    - Hardcoded fallback model names and agent defaults are guaranteed.
    """
    if name in _PROMPT_ALIASES:
        from core.prompts import get_prompt
        return get_prompt(_PROMPT_ALIASES[name])

    if name in _MODEL_DEFAULTS:
        from core.llm.config_manager import load_config, has_user_configured_keys
        cfg = load_config()
        # 1. Check user config file (~/.carole/config.json)
        from_cfg = cfg.get("default_models", {}).get(name)
        if from_cfg and isinstance(from_cfg, str) and from_cfg.strip():
            return from_cfg.strip()
        # 2. Check host environment variable ONLY if no keys were found in cfg
        if not has_user_configured_keys(cfg):
            from_env = os.getenv(name)
            if from_env and from_env.strip():
                return from_env.strip()
        # 3. Dynamic smart detection based on active API keys / hardcoded fallback
        return _get_default_model(name, cfg)

    if name in _AGENT_SETTINGS_DEFAULTS:
        from core.llm.config_manager import load_config, has_user_configured_keys
        cfg = load_config()
        # 1. Check user config file
        from_cfg = cfg.get("agent_settings", {}).get(name)
        if from_cfg is not None:
            try:
                return int(from_cfg)
            except (ValueError, TypeError):
                pass
        # 2. Check env variables ONLY if no keys were found in cfg
        if not has_user_configured_keys(cfg):
            env_map = {
                "MAX_LOOPS": "MAX_AGENT_LOOPS",
                "APPROVAL_TIMEOUT_SECS": "APPROVAL_TIMEOUT_SECS",
                "MAX_QUEUE_SIZE": "MAX_EVENT_QUEUE_SIZE"
            }
            if name in env_map:
                from_env = os.getenv(env_map[name])
                if from_env is not None:
                    try:
                        return int(from_env)
                    except (ValueError, TypeError):
                        pass
        # 3. Fallback
        return int(_AGENT_SETTINGS_DEFAULTS[name])

    raise AttributeError(f"module 'core.config' has no attribute {name!r}")
