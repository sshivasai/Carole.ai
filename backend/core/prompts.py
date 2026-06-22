"""
# backend/core/prompts.py

Central prompt registry for Carole.ai.

Priority (lowest → highest):
  1. backend/core/defaults/prompts.json  (shipped with the repo)
  2. ~/.carole/prompts.json               (user overrides, gitignored)

Usage:
    from core.prompts import get_prompt

    text = get_prompt("personality.professional", name="Nova", role="Coder")
    text = get_prompt("system.judge")

Variable substitution uses Python str.format_map(), so {braces} in the
prompt template are replaced with keyword arguments. Use {{ }} to escape
a literal brace in the prompt text.
"""

import json
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger("carole.prompts")

from core.config import CAROLE_HOME_DIR

_DEFAULTS_PATH = Path(__file__).parent / "defaults" / "prompts.json"
_USER_PATH     = CAROLE_HOME_DIR / "prompts.json"


def load_prompts() -> Dict[str, str]:
    """
    Returns the merged prompts dict: { slug: template_string }
    """
    prompts: Dict[str, str] = {}

    # 1. Load defaults
    try:
        with open(_DEFAULTS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # Strip meta keys that start with _
        prompts = {k: v for k, v in raw.items() if not k.startswith("_")}
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to load default prompts: %s", e)

    # 2. Merge user overrides
    if _USER_PATH.exists():
        try:
            with open(_USER_PATH, "r", encoding="utf-8") as f:
                user_raw = json.load(f)
            for k, v in user_raw.items():
                if not k.startswith("_"):
                    prompts[k] = v
            logger.debug("Merged user prompts from %s", _USER_PATH)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to load user prompt overrides: %s", e)

    return prompts


def save_prompts(prompts: Dict[str, str]) -> None:
    """
    Saves prompts to ~/.carole/prompts.json (user override file).
    """
    _USER_PATH.parent.mkdir(exist_ok=True)
    with open(_USER_PATH, "w", encoding="utf-8") as f:
        json.dump(prompts, f, indent=2, ensure_ascii=False)
    logger.info("Saved user prompts to %s", _USER_PATH)


def load_default_prompts() -> Dict[str, str]:
    """Returns ONLY the shipped defaults (ignores user overrides)."""
    try:
        with open(_DEFAULTS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {k: v for k, v in raw.items() if not k.startswith("_")}
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to load default prompts: %s", e)
        return {}


def reset_prompts() -> None:
    """Deletes the user override file so factory defaults take effect on next load."""
    if _USER_PATH.exists():
        _USER_PATH.unlink()
        logger.info("Deleted user prompt overrides: %s", _USER_PATH)


def get_prompt(slug: str, **kwargs) -> str:
    """
    Returns the formatted prompt for the given slug, substituting any kwargs.

    Example:
        get_prompt("personality.professional", name="Nova", role="Coder")

    Falls back to an empty string with a warning if the slug is not found.
    """
    prompts = load_prompts()
    template = prompts.get(slug)
    if template is None:
        logger.warning("Prompt slug '%s' not found — returning empty string.", slug)
        return ""
    if not kwargs:
        return template
    try:
        return template.format_map(kwargs)
    except KeyError as e:
        logger.warning("Prompt '%s' missing variable %s — returning raw template.", slug, e)
        return template


def build_agent_system_prompt(name: str, role: str, personality: str = "professional") -> str:
    """
    Assembles the full agent system prompt from modular prompt slugs.
    Replaces the old _default_system_prompt() helper in crud_routes.py.
    """
    personality_slug = f"personality.{personality}"
    base = get_prompt(personality_slug, name=name, role=role)
    if not base:
        # Fallback to professional if personality slug missing
        base = get_prompt("personality.professional", name=name, role=role)

    markdown_rules   = get_prompt("system.markdown_rules")
    behavioral_rules = get_prompt("system.behavioral_rules")
    tool_use         = get_prompt("system.tool_use")
    reasoning_rules  = get_prompt("system.reasoning_rules")

    prompt = f"{base}\n\n{markdown_rules}\n\n{behavioral_rules}\n\n{tool_use}\n\n{reasoning_rules}\n"
    
    if role.lower() in ["coordinator", "orchestrator"]:
        coordinator_directives = get_prompt("system.coordinator_directives")
        prompt += f"\n{coordinator_directives}\n"
        
    return prompt
