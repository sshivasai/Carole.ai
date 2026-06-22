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
    },
    "providers": {
        "ollama_base_url": "http://localhost:11434/v1",
    },
}


def load_config() -> dict:
    """
    Reads ~/.carole/config.json and merges with defaults.
    Returns the resolved config dictionary.
    """
    if not CONFIG_PATH.exists():
        logger.info("⚙️  [ConfigManager] config.json not found — using env vars only.")
        return _DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # Deep-merge: user config overrides defaults, but defaults fill missing keys
        merged = _DEFAULT_CONFIG.copy()
        merged["api_keys"] = {**merged["api_keys"], **raw.get("api_keys", {})}
        merged["providers"] = {**merged["providers"], **raw.get("providers", {})}
        logger.info("⚙️  [ConfigManager] Loaded config from %s", CONFIG_PATH)
        return merged
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("⚙️  [ConfigManager] Failed to read config.json: %s — using env vars.", e)
        return _DEFAULT_CONFIG.copy()


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
