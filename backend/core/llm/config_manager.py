"""
# backend/core/llm/config_manager.py

Manages application configuration stored in ~/.carole/config.json.
This file stores user-provided API keys and provider settings.

Priority order for API keys:
  1. ~/.carole/config.json (user-configured, wins)
  2. Environment variables (fallback / .env file)
"""

import json
import os
import logging
from typing import Optional
from core.config import CAROLE_HOME_DIR

logger = logging.getLogger("carole.config_manager")

CONFIG_PATH = CAROLE_HOME_DIR / "config.json"

# The schema / default shape for the config file
_DEFAULT_CONFIG = {
    "api_keys": {
        "openai": "",
        "anthropic": "",
        "google": "",
        "openrouter": "",
        "nvidia": "",
        "tavily": "",
        "browseruse": "",
    },
    "providers": {
        "ollama_base_url": "http://localhost:11434/v1",
    },
    "compaction": {
        "max_observation_chars": 4000,
        "token_trigger_ratio": 0.80,
        "context_window_size": 128000,
        "recent_messages_to_keep": 8,
    },
    "browser_automation": {
        "provider": "local",
        "api_keys": {
            "browserbase": "",
            "scraperapi": "",
            "zenrows": ""
        }
    },
    "access_control": {
        "enable_judge": True,
        "judge_fallback": "always_ask",
        "categories": {
            "view": "allow",
            "edit": "judge",
            "create": "judge",
            "delete": "always_ask",
            "execute": "judge",
            "git": "allow",
            "web": "allow",
            "browser": "allow",
            "subagents": "allow",
            "scheduler": "judge"
        },
        "overrides": {},
        "custom_skip_judge": {
            "file_patterns": [],
            "command_prefixes": []
        }
    }
}


_cached_config = None
_last_mtime = 0.0


def load_config() -> dict:
    """
    Reads ~/.carole/config.json and merges with defaults.
    Uses an mtime-based in-memory cache to avoid disk I/O latency on repeated reads.
    Returns the resolved config dictionary.
    """
    global _cached_config, _last_mtime

    if not CONFIG_PATH.exists():
        if _cached_config is None:
            logger.info("⚙️  [ConfigManager] config.json not found — using env vars only.")
            _cached_config = _DEFAULT_CONFIG.copy()
        return _cached_config

    try:
        current_mtime = os.path.getmtime(CONFIG_PATH)
        if _cached_config is not None and current_mtime == _last_mtime:
            return _cached_config

        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # Deep-merge: user config overrides defaults, but defaults fill missing keys
        merged = _DEFAULT_CONFIG.copy()
        merged["api_keys"] = {**merged["api_keys"], **raw.get("api_keys", {})}
        merged["providers"] = {**merged["providers"], **raw.get("providers", {})}
        merged["compaction"] = {**merged["compaction"], **raw.get("compaction", {})}
        
        raw_ba = raw.get("browser_automation", {})
        merged["browser_automation"] = {**merged["browser_automation"], **raw_ba}
        if "api_keys" in raw_ba:
            merged["browser_automation"]["api_keys"] = {**merged["browser_automation"]["api_keys"], **raw_ba["api_keys"]}
        
        raw_ac = raw.get("access_control", {})
        merged["access_control"] = {**merged["access_control"], **raw_ac}
        if "categories" in raw_ac:
            merged["access_control"]["categories"] = {**merged["access_control"]["categories"], **raw_ac["categories"]}
        if "overrides" in raw_ac:
            merged["access_control"]["overrides"] = {**merged["access_control"]["overrides"], **raw_ac["overrides"]}
        if "custom_skip_judge" in raw_ac:
            merged["access_control"]["custom_skip_judge"] = {**merged["access_control"]["custom_skip_judge"], **raw_ac["custom_skip_judge"]}
        
        # also pass through any other top-level keys like agent_settings or default_models
        for key, value in raw.items():
            if key not in merged:
                merged[key] = value

        logger.info("⚙️  [ConfigManager] Loaded config from %s", CONFIG_PATH)
        
        _cached_config = merged
        _last_mtime = current_mtime
        return _cached_config
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("⚙️  [ConfigManager] Failed to read config.json: %s — using env vars.", e)
        if _cached_config is None:
            _cached_config = _DEFAULT_CONFIG.copy()
        return _cached_config


def save_config(config: dict) -> None:
    """
    Writes the given config dictionary to ~/.carole/config.json.
    """
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        logger.info("⚙️  [ConfigManager] Saved config to %s", CONFIG_PATH)
    except OSError as e:
        logger.error("⚙️  [ConfigManager] Failed to write config.json: %s", e)
        raise


def get_key(config: dict, config_key: str, env_var: str) -> Optional[str]:
    """
    Resolves a single API key with priority: config.json → env var.
    Returns None if neither is set or the value is an empty string.
    """
    value = config.get("api_keys", {}).get(config_key, "").strip()
    if value:
        return value
    return os.getenv(env_var) or None
