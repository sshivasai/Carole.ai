"""
# backend/core/llm/config_manager.py

Manages application configuration stored in ~/.carole/config.json.
This file stores user-provided API keys and provider settings.

Priority order for API keys:
  1. ~/.carole/config.json (user-configured, wins)
  2. Environment variables (fallback / .env file)
"""

import json
import logging
import math
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from core.config import CAROLE_HOME_DIR

logger = logging.getLogger("carole.config_manager")

CONFIG_PATH = Path(CAROLE_HOME_DIR) / "config.json"

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
    "default_models": {
        "DEFAULT_FAST_MODEL": "",
        "DEFAULT_SMART_MODEL": "",
        "DEFAULT_CODER_MODEL": "",
        "DEFAULT_JUDGE_MODEL": "",
        "DEFAULT_EMBEDDING_MODEL": "",
    },
    "agent_settings": {
        "MAX_LOOPS": 25,
        "APPROVAL_TIMEOUT_SECS": 60,
        "MAX_QUEUE_SIZE": 500,
        "DREAM_INTERVAL_MINUTES": 15,
        "MEMORY_RETRIEVAL_LIMIT": 5,
        "CONTEXT_COMPACTION_THRESHOLD": 15,
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


class ConfigError(RuntimeError):
    """Configuration could not be read, validated, or persisted."""


_cached_config: Optional[dict] = None
_cached_signature: Optional[tuple[int, int, int, int]] = None
_config_lock = threading.RLock()


def _reject_json_constant(value: str):
    raise ValueError("Non-finite JSON numbers are not supported")


def _validate_shape(value, default, path: str = "config") -> None:
    """Validate known settings without rejecting extension/plugin settings."""
    if isinstance(default, dict):
        if not isinstance(value, dict):
            raise ConfigError(f"{path} must be an object")
        for key, child in value.items():
            if not isinstance(key, str):
                raise ConfigError(f"{path} must contain string keys")
            if key in default:
                _validate_shape(child, default[key], f"{path}.{key}")
        return

    if isinstance(default, bool):
        valid = isinstance(value, bool)
    elif isinstance(default, int):
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif isinstance(default, float):
        valid = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    elif isinstance(default, list):
        valid = isinstance(value, list)
    else:
        valid = isinstance(value, type(default))

    if not valid:
        raise ConfigError(f"{path} has an invalid value type")


def _deep_merge(defaults: dict, overrides: dict) -> dict:
    merged = deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _resolve_config(raw: dict) -> dict:
    _validate_shape(raw, _DEFAULT_CONFIG)
    resolved = _deep_merge(_DEFAULT_CONFIG, raw)

    for section_name, keys in (
        ("api_keys", resolved["api_keys"]),
        ("browser_automation.api_keys", resolved["browser_automation"]["api_keys"]),
        ("default_models", resolved.get("default_models", {})),
    ):
        for name, value in keys.items():
            if not isinstance(value, str):
                raise ConfigError(f"{section_name}.{name} must be a string")

    for name, value in resolved.get("agent_settings", {}).items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 1:
            raise ConfigError(f"agent_settings.{name} must be a positive number")
        resolved["agent_settings"][name] = int(value)

    compaction = resolved["compaction"]
    if compaction["max_observation_chars"] < 1:
        raise ConfigError("compaction.max_observation_chars must be positive")
    if compaction["context_window_size"] < 1:
        raise ConfigError("compaction.context_window_size must be positive")
    if compaction["recent_messages_to_keep"] < 1:
        raise ConfigError("compaction.recent_messages_to_keep must be positive")
    if not 0 < compaction["token_trigger_ratio"] <= 1:
        raise ConfigError("compaction.token_trigger_ratio must be in (0, 1]")

    for name in ("file_patterns", "command_prefixes"):
        entries = resolved["access_control"]["custom_skip_judge"][name]
        if any(not isinstance(entry, str) or not entry.strip() for entry in entries):
            raise ConfigError(
                f"access_control.custom_skip_judge.{name} "
                "must contain nonempty strings"
            )

    base_url = resolved["providers"]["ollama_base_url"].strip()
    if base_url:
        try:
            parsed = urlsplit(base_url)
            _ = parsed.port  # Validate the port, if supplied.
        except ValueError:
            raise ConfigError("providers.ollama_base_url is invalid") from None

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ConfigError(
                "providers.ollama_base_url must be an HTTP(S) URL "
                "without credentials, query parameters, or a fragment"
            )

        resolved["providers"]["ollama_base_url"] = base_url.rstrip("/")

    return resolved


def _file_signature(stat_result: os.stat_result) -> tuple[int, int, int, int]:
    return (
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
        stat_result.st_ctime_ns,
    )


def load_config() -> dict:
    """
    Return an independent configuration snapshot.

    Missing files use defaults. Invalid/unreadable files raise ConfigError:
    silently substituting defaults could weaken access-control settings.

    Call from asyncio.to_thread() when used in an async request handler.
    """
    global _cached_config, _cached_signature

    with _config_lock:
        try:
            signature = _file_signature(CONFIG_PATH.stat())
        except FileNotFoundError:
            # Do not retain old credentials after the file has been removed.
            _cached_config = None
            _cached_signature = None
            return deepcopy(_DEFAULT_CONFIG)
        except OSError:
            raise ConfigError("Could not inspect the configuration file") from None

        if _cached_config is not None and signature == _cached_signature:
            return deepcopy(_cached_config)

        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as handle:
                raw = json.load(handle, parse_constant=_reject_json_constant)
                # Describe the file actually read, including across atomic replacement.
                loaded_signature = _file_signature(os.fstat(handle.fileno()))

            resolved = _resolve_config(raw)
        except ConfigError:
            raise
        except (OSError, UnicodeError, ValueError, RecursionError):
            # Do not include file contents or credentials in errors/logs.
            raise ConfigError("Could not read a valid configuration file") from None

        _cached_config = resolved
        _cached_signature = loaded_signature
        return deepcopy(resolved)


def save_config(config: dict) -> None:
    """
    Atomically replace the complete configuration.

    This is replacement, not PATCH or a cross-process read-modify-write
    transaction. Concurrent settings updates require versioning/locking in
    the settings service.

    POSIX files are created owner-readable/writable only. Windows deployments
    must additionally secure the configuration directory with an appropriate ACL.
    """
    global _cached_config, _cached_signature

    with _config_lock:
        resolved = _resolve_config(config)

        try:
            serialized = json.dumps(
                resolved, indent=2, ensure_ascii=False, allow_nan=False
            ) + "\n"
        except (TypeError, ValueError, RecursionError):
            raise ConfigError("Configuration must contain valid JSON values") from None

        temporary_path: Optional[Path] = None
        fd: Optional[int] = None

        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{CONFIG_PATH.name}.",
                suffix=".tmp",
                dir=CONFIG_PATH.parent,
            )
            temporary_path = Path(temporary_name)

            if os.name == "posix":
                os.fchmod(fd, 0o600)

            handle = os.fdopen(fd, "w", encoding="utf-8")
            fd = None  # The file object now owns the descriptor.

            with handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(temporary_path, CONFIG_PATH)
            temporary_path = None

            # Other processes independently invalidate their stat-based caches.
            _cached_config = None
            _cached_signature = None

            if os.name == "posix":
                directory_fd = os.open(
                    CONFIG_PATH.parent,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                )
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)

        except OSError:
            # An fsync failure can occur after replacement; force a fresh read.
            _cached_config = None
            _cached_signature = None
            raise ConfigError(
                "Configuration persistence failed; reload before retrying"
            ) from None
        finally:
            if fd is not None:
                os.close(fd)
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove a temporary configuration file")

        logger.info("Configuration saved")


def has_user_configured_keys(config: dict) -> bool:
    """
    Check if the user has configured at least one API key in ~/.carole/config.json.
    Inspects both `api_keys` and `browser_automation.api_keys`.

    When True: The application must use ONLY the user's config keys and NEVER
    fall back to host environment variables.
    When False (zero keys in cfg): Graceful fallback to host environment variables is permitted.
    """
    api_keys = config.get("api_keys", {})
    if isinstance(api_keys, dict):
        if any(isinstance(v, str) and v.strip() for v in api_keys.values()):
            return True

    ba_keys = config.get("browser_automation", {}).get("api_keys", {})
    if isinstance(ba_keys, dict):
        if any(isinstance(v, str) and v.strip() for v in ba_keys.values()):
            return True

    return False


def get_key(config: dict, config_key: str, env_var: Optional[str] = None) -> Optional[str]:
    """
    Resolve an API key.
    - If user provided keys in ~/.carole/config.json (has_user_configured_keys is True):
      returns only the key from config.json (or None if not set). Never falls back to host environment.
    - Only falls back to host environment variable if NO keys were found anywhere in cfg.
    """
    keys = config.get("api_keys", {})
    if not isinstance(keys, dict):
        raise ConfigError("api_keys must be an object")

    value = keys.get(config_key, "")
    if not isinstance(value, str):
        raise ConfigError(f"api_keys.{config_key} must be a string")

    stripped = value.strip()
    if stripped:
        return stripped

    # If the user has configured keys in config.json, do not leak host environment variables!
    if has_user_configured_keys(config):
        return None

    # Only fallback to host environment variable if no keys were found in cfg at all
    if env_var:
        env_val = os.getenv(env_var, "").strip()
        if env_val:
            return env_val

    return None


def get_browser_key(config: dict, provider_key: str, env_var: Optional[str] = None) -> Optional[str]:
    """
    Resolve a browser automation API key (browserbase, scraperapi, zenrows).
    Checks config["browser_automation"]["api_keys"] and config["api_keys"].
    - If user provided keys in ~/.carole/config.json, only uses keys from config.json.
    - Only falls back to host environment if no keys were found in cfg at all.
    """
    ba_keys = config.get("browser_automation", {}).get("api_keys", {})
    if isinstance(ba_keys, dict):
        val = ba_keys.get(provider_key, "")
        if isinstance(val, str) and val.strip():
            return val.strip()

    # Also check top-level api_keys
    api_keys = config.get("api_keys", {})
    if isinstance(api_keys, dict):
        val = api_keys.get(provider_key, "")
        if isinstance(val, str) and val.strip():
            return val.strip()

    if has_user_configured_keys(config):
        return None

    if env_var:
        env_val = os.getenv(env_var, "").strip()
        if env_val:
            return env_val

    return None

