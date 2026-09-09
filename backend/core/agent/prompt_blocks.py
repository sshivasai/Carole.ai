"""
core/agent/prompt_blocks.py

Loads and manages the editable system prompt blocks that are injected into
every agent's system prompt via assemble_system_prompt().

Flow:
  1. Defaults are read from core/defaults/prompts.json  (keys: "block.*")
  2. User overrides are stored in ~/.carole/config.json  under "prompt_blocks"
     Each entry: { "enabled": bool, "content": str }
  3. get_block(key, **vars) returns the formatted string or None if disabled.
  4. API routes expose GET/PUT /settings/prompt-blocks and
     POST /settings/prompt-blocks/{key}/reset
"""

import json
import logging
from pathlib import Path
from typing import Optional

from core.config import CAROLE_HOME_DIR
from core.llm.config_manager import load_config, save_config

logger = logging.getLogger("carole.prompt_blocks")

# Path to the canonical defaults file
_DEFAULTS_PATH = Path(__file__).parent.parent / "defaults" / "prompts.json"

# Human-readable metadata for the Settings UI
BLOCK_META: dict[str, dict] = {
    "scratchpads": {
        "display_name": "Scratchpad Tools",
        "description": "Explains personal & team scratchpad tools to agents.",
        "category": "Memory",
    },
    "docs": {
        "display_name": "Documentation Files",
        "description": "Rules for frictionless .md / .txt file creation.",
        "category": "Filesystem",
    },
    "workspace_paths": {
        "display_name": "Temp File Paths",
        "description": "Mandatory .carole/ scratch-file path rule. Use {carole_dir} as a placeholder — it is replaced at runtime.",
        "category": "Filesystem",
    },
    "scheduler": {
        "display_name": "Cron Scheduler",
        "description": "Documents scheduled task tools and cron expression syntax.",
        "category": "Automation",
    },
    "browser": {
        "display_name": "Browser Automation",
        "description": "3-tier browser automation system (Playwright MCP → built-in tools → script).",
        "category": "Browser",
    },
}


def _load_defaults() -> dict[str, str]:
    """Load block defaults from core/defaults/prompts.json (keys starting with 'block.')."""
    try:
        data = json.loads(_DEFAULTS_PATH.read_text(encoding="utf-8"))
        return {
            k.removeprefix("block."): v
            for k, v in data.items()
            if k.startswith("block.")
        }
    except Exception as e:
        logger.warning("[PromptBlocks] Could not load defaults: %s", e)
        return {}


def _load_overrides() -> dict[str, dict]:
    """Load user overrides from ~/.carole/config.json prompt_blocks section."""
    try:
        cfg = load_config()
        raw = cfg.get("prompt_blocks", {})
        if not isinstance(raw, dict):
            return {}
        return {key: {field: value for field, value in entry.items()
                      if (field == "content" and isinstance(value, str)) or
                         (field == "enabled" and isinstance(value, bool))}
                for key, entry in raw.items() if key in BLOCK_META and isinstance(entry, dict)}
    except Exception as e:
        logger.warning("[PromptBlocks] Could not load config overrides: %s", e)
        return {}


def _save_overrides(overrides: dict) -> None:
    """Persist prompt_blocks overrides back to config.json."""
    cfg = load_config()
    cfg["prompt_blocks"] = overrides
    save_config(cfg)


def list_blocks() -> list[dict]:
    """
    Return the full block list for the Settings UI.
    Each item: { key, display_name, description, category, enabled, content, is_customized }
    """
    defaults = _load_defaults()
    overrides = _load_overrides()

    result = []
    for key, meta in BLOCK_META.items():
        default_content = defaults.get(key, "")
        override = overrides.get(key, {})
        content = override.get("content", default_content)
        enabled = override.get("enabled", True)
        is_customized = key in overrides and (
            override.get("content", default_content) != default_content
            or not override.get("enabled", True)
        )
        result.append({
            "key": key,
            "display_name": meta["display_name"],
            "description": meta["description"],
            "category": meta["category"],
            "enabled": enabled,
            "content": content,
            "default_content": default_content,
            "is_customized": is_customized,
        })
    return result


def save_blocks(updates: list[dict]) -> None:
    """
    Persist a list of { key, enabled, content } updates.
    Only stores keys that differ from the default (resets are handled by delete).
    """
    defaults = _load_defaults()
    overrides = _load_overrides()

    for item in updates:
        key = item.get("key", "")
        if key not in BLOCK_META:
            continue
        default_content = defaults.get(key, "")
        new_content = item.get("content", default_content)
        new_enabled = item.get("enabled", True)
        if not isinstance(new_content, str) or not isinstance(new_enabled, bool):
            raise ValueError("Prompt block content must be a string and enabled must be a boolean")

        # Store the override (even if content matches default, enabled flag may differ)
        overrides[key] = {
            "enabled": new_enabled,
            "content": new_content,
        }

    _save_overrides(overrides)


def reset_block(key: str) -> dict:
    """Remove the user override for a single block, restoring the default."""
    if key not in BLOCK_META:
        raise ValueError(f"Unknown block key: {key!r}")
    overrides = _load_overrides()
    overrides.pop(key, None)
    _save_overrides(overrides)
    defaults = _load_defaults()
    return {
        "key": key,
        "content": defaults.get(key, ""),
        "enabled": True,
        "is_customized": False,
    }


def get_block(key: str, **template_vars) -> Optional[str]:
    """
    Returns the rendered block content, or None if disabled.
    Template variables (e.g. carole_dir=...) are substituted into {placeholders}.
    """
    defaults = _load_defaults()
    overrides = _load_overrides()

    override = overrides.get(key, {})
    enabled = override.get("enabled", True)
    if not enabled:
        return None

    content = override.get("content", defaults.get(key, ""))
    if not content:
        return None

    # Substitute runtime variables safely
    if template_vars:
        try:
            from core.agent.prompt_safety import render_template
            content = render_template(content, template_vars)
        except (KeyError, ValueError):
            pass  # Leave unresolved placeholders as-is

    return content + "\n\n"
