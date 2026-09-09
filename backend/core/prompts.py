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

Variable substitution replaces only supplied plain {name} placeholders.
JSON braces, attribute expressions, and unknown placeholders remain literal.
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict

logger = logging.getLogger("carole.prompts")

from core.config import CAROLE_HOME_DIR

_DEFAULTS_PATH = Path(__file__).parent / "defaults" / "prompts.json"
_USER_PATH     = CAROLE_HOME_DIR / "prompts.json"


# ---------------------------------------------------------------------------
# Prompt cache — keyed by (defaults_mtime, user_mtime).
# Invalidated automatically whenever either JSON file changes on disk so
# hot-reload via the Settings UI works without a server restart.
# ---------------------------------------------------------------------------
_prompt_cache: Dict[str, str] = {}
_prompt_cache_key: tuple = (0.0, 0.0)


def _get_mtimes() -> tuple:
    """Return (defaults_mtime, user_mtime) — user file mtime is 0.0 if absent."""
    try:
        dm = _DEFAULTS_PATH.stat().st_mtime
    except OSError:
        dm = 0.0
    try:
        um = _USER_PATH.stat().st_mtime if _USER_PATH.exists() else 0.0
    except OSError:
        um = 0.0
    return (dm, um)


def _invalidate_prompt_cache() -> None:
    """Force-clears the in-memory cache (call after save_prompts)."""
    global _prompt_cache, _prompt_cache_key
    _prompt_cache = {}
    _prompt_cache_key = (0.0, 0.0)


def load_prompts() -> Dict[str, str]:
    """
    Returns the merged prompts dict: { slug: template_string }

    Results are cached in process memory and invalidated automatically
    whenever the defaults or user-override JSON files change on disk.
    """
    global _prompt_cache, _prompt_cache_key

    current_key = _get_mtimes()
    if current_key == _prompt_cache_key and _prompt_cache:
        return dict(_prompt_cache)

    prompts: Dict[str, str] = {}

    # 1. Load defaults
    try:
        with open(_DEFAULTS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # Strip meta keys that start with _
        if not isinstance(raw, dict) or any(not isinstance(v, str) for k, v in raw.items() if not k.startswith("_")):
            raise RuntimeError("Default prompts must be a string-valued object")
        prompts = {k: v for k, v in raw.items() if not k.startswith("_")}
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to load default prompts: %s", e)

    # Hard-fail if the shipped defaults are missing/corrupted — agents would
    # otherwise run with blank system prompts.
    if not prompts:
        raise RuntimeError(
            f"Failed to load prompts from {_DEFAULTS_PATH} — file is empty or corrupted"
        )
    for _critical in ("system.behavioral_rules", "system.tool_use", "personality.professional"):
        if _critical not in prompts:
            logger.warning("Critical prompt slug '%s' missing from %s", _critical, _DEFAULTS_PATH)

    # 2. Merge user overrides
    if _USER_PATH.exists():
        try:
            with open(_USER_PATH, "r", encoding="utf-8") as f:
                user_raw = json.load(f)
            if not isinstance(user_raw, dict):
                raise ValueError("Prompt overrides must be an object")
            for k, v in user_raw.items():
                if not k.startswith("_") and isinstance(v, str):
                    prompts[k] = v
            logger.debug("Merged user prompts from %s", _USER_PATH)
        except (OSError, ValueError) as e:
            logger.warning("Failed to load user prompt overrides: %s", e)

    # Store in cache
    _prompt_cache = prompts
    _prompt_cache_key = current_key
    return dict(prompts)


def save_prompts(prompts: Dict[str, str]) -> None:
    """
    Saves prompts to ~/.carole/prompts.json (user override file).
    """
    if not isinstance(prompts, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in prompts.items()):
        raise ValueError("Prompts must map string names to string templates")
    _USER_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=_USER_PATH.parent, prefix=".prompts-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(prompts, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, _USER_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    _invalidate_prompt_cache()  # Force cache refresh on next get_prompt call
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
        from core.agent.prompt_safety import render_template
        return render_template(template, kwargs)
    except Exception as e:
        logger.warning("get_prompt('%s') format error: %s — returning raw template", slug, e)
        return template


def build_agent_system_prompt(name: str, role: str, personality: str = "professional") -> str:
    """
    Assembles the full agent system prompt from modular prompt slugs.
    Replaces the old _default_system_prompt() helper in crud_routes.py.

    Prompt structure (top to bottom):
      1. Personality tone (personality.*)
      2. Role cognitive framework (role.*)      ← NEW
      3. Unified system rules (behavioral, tool_use, markdown, reasoning)
      4. Coordinator directives (only if role is coordinator/orchestrator)
    """
    personality_slug = f"personality.{personality}"
    base = get_prompt(personality_slug, name=name, role=role)
    if not base:
        # Fallback to professional if personality slug missing
        base = get_prompt("personality.professional", name=name, role=role)

    # --- Role-specific cognitive framework ---
    # Normalize role names: "Coordinator" → "orchestrator", "Coder" → "coder", etc.
    _ROLE_ALIASES = {
        "coordinator": "orchestrator",
        "software engineer": "coder",
        "python developer": "coder",
        "python engineer": "coder",
        "backend developer": "coder",
        "frontend developer": "coder",
        "full stack developer": "coder",
        "web developer": "coder",
        "code reviewer": "reviewer",
        "technical writer": "writer",
        "documentation specialist": "writer",
        "research analyst": "researcher",
        "data analyst": "analyst",
        "devops engineer": "devops",
        "test engineer": "tester",
        "qa engineer": "tester",
        "ui/ux designer": "coder",   # Designers use coder framework
    }
    role_key = role.strip().lower()
    role_key = _ROLE_ALIASES.get(role_key, role_key)
    role_prompt = get_prompt(f"role.{role_key}", name=name, role=role)
    if not role_prompt and ("developer" in role_key or "engineer" in role_key or "programmer" in role_key):
        role_prompt = get_prompt("role.coder", name=name, role=role)

    markdown_rules   = get_prompt("system.markdown_rules")
    behavioral_rules = get_prompt("system.behavioral_rules", name=name, role=role)
    tool_use         = get_prompt("system.tool_use")
    reasoning_rules  = get_prompt("system.reasoning_rules")

    # Assemble: personality → role framework → unified rules
    parts = [base]
    if role_prompt:
        parts.append(role_prompt)
    parts.extend([markdown_rules, behavioral_rules, tool_use, reasoning_rules])

    prompt = "\n\n".join(p for p in parts if p) + "\n"
    
    if role_key in ["coordinator", "orchestrator"]:
        coordinator_directives = get_prompt("system.coordinator_directives")
        prompt += f"\n{coordinator_directives}\n"
        
    return prompt


# Backward compatibility alias
build_system_prompt = build_agent_system_prompt
