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
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("carole.model_catalog")

from core.config import CAROLE_HOME_DIR

_DEFAULTS_PATH = Path(__file__).parent.parent / "defaults" / "supported_models.json"
_USER_PATH     = CAROLE_HOME_DIR / "supported_models.json"


class ModelCatalogError(ValueError):
    """Raised when model catalog validation fails."""


def model_limits(model_id: str) -> dict:
    """Use explicit catalog metadata; never infer independent limits from a label."""
    for provider in load_model_catalog().values():
        for entry in provider.get("models", []):
            if entry.get("value") == model_id:
                return {key: entry[key] for key in ("context_window", "input_limit", "output_limit")
                        if isinstance(entry.get(key), int) and not isinstance(entry[key], bool) and entry[key] > 0}
    return {}


def _validate_model_catalog(catalog: Any) -> None:
    """
    Validates that a model catalog conforms to the required shape:
    {
      "provider_id": {
        "label": "Provider Name",
        "key_name": "PROVIDER_KEY" | None,
        "models": [
          { "value": "model-id", "label": "Model Name", "special": True/False }
        ]
      }
    }
    """
    if not isinstance(catalog, dict):
        raise ModelCatalogError(f"Model catalog must be a JSON object/dict, got {type(catalog).__name__}.")

    for provider_id, provider_data in catalog.items():
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ModelCatalogError(f"Provider ID must be a non-empty string, got {provider_id!r}.")
        if not isinstance(provider_data, dict):
            raise ModelCatalogError(
                f"Provider data for '{provider_id}' must be a dictionary, got {type(provider_data).__name__}."
            )

        label = provider_data.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ModelCatalogError(f"Provider '{provider_id}' missing required non-empty string 'label'.")

        key_name = provider_data.get("key_name")
        if key_name is not None and (not isinstance(key_name, str) or not key_name.strip()):
            raise ModelCatalogError(
                f"Provider '{provider_id}' key_name must be a non-empty string or None, got {key_name!r}."
            )

        models = provider_data.get("models")
        if not isinstance(models, list):
            raise ModelCatalogError(
                f"Provider '{provider_id}' models must be a list, got {type(models).__name__}."
            )

        for idx, model in enumerate(models):
            if not isinstance(model, dict):
                raise ModelCatalogError(
                    f"Model #{idx} for provider '{provider_id}' must be a dictionary, got {type(model).__name__}."
                )
            model_val = model.get("value")
            if not isinstance(model_val, str) or not model_val.strip():
                raise ModelCatalogError(
                    f"Model #{idx} for provider '{provider_id}' missing required non-empty string 'value'."
                )
            model_lbl = model.get("label")
            if not isinstance(model_lbl, str) or not model_lbl.strip():
                raise ModelCatalogError(
                    f"Model #{idx} ({model_val}) for provider '{provider_id}' missing required non-empty string 'label'."
                )


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
            _validate_model_catalog(catalog)
    except (OSError, json.JSONDecodeError, ModelCatalogError) as e:
        logger.error("Failed to load or validate default model catalog: %s", e)

    # 2. Deep-merge user overrides if present
    if _USER_PATH.exists():
        try:
            with open(_USER_PATH, "r", encoding="utf-8") as f:
                user_catalog = json.load(f)
            _validate_model_catalog(user_catalog)
            for provider_id, provider_data in user_catalog.items():
                # User override replaces the provider entry entirely
                catalog[provider_id] = provider_data
            logger.debug("Merged user model catalog from %s", _USER_PATH)
        except (OSError, json.JSONDecodeError, ModelCatalogError) as e:
            logger.warning("Failed to load user model catalog override (%s): %s", _USER_PATH, e)

    return catalog


def save_model_catalog(catalog: Dict[str, dict]) -> None:
    """
    Validates and saves the given catalog atomically to ~/.carole/supported_models.json.
    """
    # 1. Validate catalog shape, provider IDs, and model entries
    _validate_model_catalog(catalog)

    # 2. Ensure destination directory exists (with parents=True)
    target_dir = _USER_PATH.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    # 3. Write atomically via tempfile in the same filesystem directory + os.replace()
    fd, temp_file_path = tempfile.mkstemp(
        prefix="supported_models_",
        suffix=".tmp",
        dir=str(target_dir),
    )

    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_file_path, _USER_PATH)
        logger.info("Saved user model catalog to %s", _USER_PATH)
    except Exception as exc:
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass
        logger.error("Failed to save model catalog to %s: %s", _USER_PATH, exc)
        raise


def load_default_model_catalog() -> Dict[str, dict]:
    """Returns ONLY the shipped defaults (ignores any user overrides)."""
    try:
        with open(_DEFAULTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            _validate_model_catalog(data)
            return data
    except (OSError, json.JSONDecodeError, ModelCatalogError) as e:
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
    active_keys = cfg.get("api_keys", {}) if isinstance(cfg, dict) else {}
    result: Dict[str, dict] = {}
    for provider_id, provider_data in catalog.items():
        key_name = provider_data.get("key_name")
        if key_name is None or active_keys.get(key_name, "").strip():
            result[provider_id] = provider_data
    return result
