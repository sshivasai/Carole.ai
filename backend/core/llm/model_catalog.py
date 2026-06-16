"""
# backend/core/llm/model_catalog.py

Single source-of-truth for LLM provider/model definitions.

Priority (lowest → highest):
  1. backend/core/defaults/supported_models.json  (shipped with the repo)
  2. ~/.carole/supported_models.json               (user overrides, gitignored)

The user file is deep-merged on top of defaults at the provider level:
- If the user adds a new provider key, it is appended.
- If the user has the same provider key, their models list completely replaces
  the default for that provider (so they can prune models they don't use).

Hot-reload: catalog is re-read on every call to load_model_catalog().
For performance in tight loops, call it once per request, not per token.
"""

import json
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger("carole.model_catalog")

from core.config import CAROLE_HOME_DIR

_DEFAULTS_PATH = Path(__file__).parent.parent / "defaults" / "supported_models.json"
_USER_PATH     = CAROLE_HOME_DIR / "supported_models.json"


def load_model_catalog() -> Dict[str, dict]:
    """
    Returns the merged model catalog dict.
    Schema: { provider_id: { label, key_name, models: [{value, label, special?}] } }
    """
    catalog: Dict[str, dict] = {}

    # 1. Load defaults (must exist)
    try:
        with open(_DEFAULTS_PATH, "r", encoding="utf-8") as f:
            catalog = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to load default model catalog: %s", e)

    # 2. Deep-merge user overrides if present
    if _USER_PATH.exists():
        try:
            with open(_USER_PATH, "r", encoding="utf-8") as f:
                user_catalog = json.load(f)
            for provider_id, provider_data in user_catalog.items():
                # User override replaces the provider entry entirely
                catalog[provider_id] = provider_data
            logger.debug("Merged user model catalog from %s", _USER_PATH)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to load user model catalog override: %s", e)

    return catalog


def save_model_catalog(catalog: Dict[str, dict]) -> None:
    """
    Saves the given catalog to ~/.carole/supported_models.json (user override file).
    """
    _USER_PATH.parent.mkdir(exist_ok=True)
    with open(_USER_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    logger.info("Saved user model catalog to %s", _USER_PATH)


def load_default_model_catalog() -> Dict[str, dict]:
    """Returns ONLY the shipped defaults (ignores any user overrides)."""
    try:
        with open(_DEFAULTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to load default model catalog: %s", e)
        return {}


def reset_model_catalog() -> None:
    """Deletes the user override file so defaults take effect on next load."""
    if _USER_PATH.exists():
        _USER_PATH.unlink()
        logger.info("Deleted user model catalog override: %s", _USER_PATH)


def get_active_catalog(cfg: dict) -> Dict[str, dict]:
    """
    Returns the catalog filtered to providers with active API keys.
    Ollama (key_name=None) is always included.
    """
    catalog = load_model_catalog()
    active_keys = cfg.get("api_keys", {})
    result: Dict[str, dict] = {}
    for provider_id, provider_data in catalog.items():
        key_name = provider_data.get("key_name")
        if key_name is None or active_keys.get(key_name, "").strip():
            result[provider_id] = provider_data
    return result
