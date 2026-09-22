"""
# backend/tests/test_config_isolation.py

Comprehensive tests for:
1. Strict user config isolation (UI / config.json takes precedence).
2. Host environment variables are NEVER leaked when config.json has user keys.
3. Fallback to host environment variables ONLY when config.json has zero keys.
4. Dynamic model defaults and agent settings resolution.
5. Key clearing support in save_settings API.
"""

import os
import pytest
from unittest.mock import patch

from core.llm.config_manager import (
    has_user_configured_keys,
    get_key,
    get_browser_key,
)
import core.config
from core.config import _get_default_model


def test_has_user_configured_keys():
    # Empty config
    assert has_user_configured_keys({}) is False
    assert has_user_configured_keys({"api_keys": {}}) is False
    assert has_user_configured_keys({"api_keys": {"openai": "", "google": "   "}}) is False
    assert has_user_configured_keys({"browser_automation": {"api_keys": {"browserbase": ""}}}) is False

    # Config with an API key
    assert has_user_configured_keys({"api_keys": {"openai": "sk-user-key"}}) is True
    assert has_user_configured_keys({"api_keys": {"tavily": "tvly-test"}}) is True

    # Config with a browser automation key
    assert has_user_configured_keys({
        "api_keys": {"openai": ""},
        "browser_automation": {"api_keys": {"browserbase": "bb-key-123"}}
    }) is True


def test_get_key_isolation_blocks_host_env(monkeypatch):
    """When user has configured keys in config.json, host env vars must NEVER leak."""
    monkeypatch.setenv("GOOGLE_API_KEY", "host-secret-google")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "host-secret-anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "host-secret-openai")

    # User configured ONLY OpenAI in the UI
    user_cfg = {
        "api_keys": {
            "openai": "sk-user-openai",
            "google": "",
            "anthropic": "",
            "openrouter": ""
        }
    }

    # Configured key returns user's key
    assert get_key(user_cfg, "openai", "OPENAI_API_KEY") == "sk-user-openai"

    # Unconfigured keys must return None, NOT host env values!
    assert get_key(user_cfg, "google", "GOOGLE_API_KEY") is None
    assert get_key(user_cfg, "anthropic", "ANTHROPIC_API_KEY") is None
    assert get_key(user_cfg, "openrouter", "OPENROUTER_API_KEY") is None


def test_get_key_fallback_when_no_keys_in_cfg(monkeypatch):
    """When config.json has zero keys, fallback to host environment variables is allowed."""
    monkeypatch.setenv("OPENAI_API_KEY", "host-fallback-openai")
    monkeypatch.setenv("GOOGLE_API_KEY", "host-fallback-google")

    empty_cfg = {
        "api_keys": {
            "openai": "",
            "google": "",
        }
    }

    assert get_key(empty_cfg, "openai", "OPENAI_API_KEY") == "host-fallback-openai"
    assert get_key(empty_cfg, "google", "GOOGLE_API_KEY") == "host-fallback-google"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert get_key(empty_cfg, "anthropic", "ANTHROPIC_API_KEY") is None


def test_get_browser_key_isolation(monkeypatch):
    monkeypatch.setenv("BROWSERBASE_API_KEY", "host-bb-key")

    # User configured keys in UI, but left browserbase empty
    user_cfg = {
        "api_keys": {"openai": "sk-user-key"},
        "browser_automation": {"api_keys": {"browserbase": ""}}
    }
    # Must NOT leak host environment variable
    assert get_browser_key(user_cfg, "browserbase", "BROWSERBASE_API_KEY") is None

    # When user provided browserbase key in UI
    user_cfg["browser_automation"]["api_keys"]["browserbase"] = "user-bb-key"
    assert get_browser_key(user_cfg, "browserbase", "BROWSERBASE_API_KEY") == "user-bb-key"

    # When config has zero keys, fallback is allowed
    empty_cfg = {"api_keys": {}, "browser_automation": {"api_keys": {}}}
    assert get_browser_key(empty_cfg, "browserbase", "BROWSERBASE_API_KEY") == "host-bb-key"


def test_dynamic_model_selection_with_user_openai_key(monkeypatch):
    """If user configures only OpenAI, models adapt to OpenAI without leaking host Google/Anthropic."""
    monkeypatch.setenv("GOOGLE_API_KEY", "host-leaked-google")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "host-leaked-anthropic")

    user_cfg = {
        "api_keys": {"openai": "sk-user-only-key", "google": "", "anthropic": ""},
        "default_models": {}
    }

    assert _get_default_model("DEFAULT_SMART_MODEL", user_cfg) == "openai/gpt-4o"
    assert _get_default_model("DEFAULT_CODER_MODEL", user_cfg) == "openai/gpt-4o"
    assert _get_default_model("DEFAULT_FAST_MODEL", user_cfg) == "openai/gpt-4o-mini"
    assert _get_default_model("DEFAULT_JUDGE_MODEL", user_cfg) == "openai/gpt-4o-mini"
    assert _get_default_model("DEFAULT_EMBEDDING_MODEL", user_cfg) == "openai/text-embedding-3-small"


def test_dynamic_model_selection_with_user_google_key(monkeypatch):
    """If user configures only Google in UI, models adapt to Google."""
    monkeypatch.setenv("OPENAI_API_KEY", "host-openai")

    user_cfg = {
        "api_keys": {"google": "AIzaSy-user-key", "openai": "", "anthropic": ""},
        "default_models": {}
    }

    assert _get_default_model("DEFAULT_SMART_MODEL", user_cfg) == "gemini-3.6-flash"
    assert _get_default_model("DEFAULT_CODER_MODEL", user_cfg) == "gemini-3.6-flash"
    assert _get_default_model("DEFAULT_FAST_MODEL", user_cfg) == "gemini-3.6-flash"
    assert _get_default_model("DEFAULT_JUDGE_MODEL", user_cfg) == "gemini-3.6-flash"
    assert _get_default_model("DEFAULT_EMBEDDING_MODEL", user_cfg) == "models/text-embedding-004"


def test_google_auto_default_falls_forward_to_discovered_stable_flash(monkeypatch):
    monkeypatch.setattr(
        "core.config._available_google_model_ids",
        lambda: {"gemini-3.7-flash", "gemini-3.8-flash", "gemini-3.8-live"},
    )
    user_cfg = {
        "api_keys": {"google": "user-key", "openai": "", "anthropic": ""},
        "default_models": {},
    }

    assert _get_default_model("DEFAULT_FAST_MODEL", user_cfg) == "gemini-3.8-flash"


def test_google_explicit_default_is_not_overridden_by_discovery(monkeypatch):
    monkeypatch.setattr(
        "core.config._available_google_model_ids",
        lambda: {"gemini-3.8-flash"},
    )
    user_cfg = {
        "api_keys": {"google": "user-key"},
        "default_models": {"DEFAULT_FAST_MODEL": "gemini-custom-tuned"},
    }

    assert _get_default_model("DEFAULT_FAST_MODEL", user_cfg) == "gemini-custom-tuned"


def test_dynamic_model_selection_with_user_anthropic_key(monkeypatch):
    """If user configures only Anthropic in UI, models adapt to Anthropic."""
    user_cfg = {
        "api_keys": {"anthropic": "sk-ant-user-key", "openai": "", "google": ""},
        "default_models": {}
    }

    assert _get_default_model("DEFAULT_CODER_MODEL", user_cfg) == "claude-3-5-sonnet-latest"
    assert _get_default_model("DEFAULT_SMART_MODEL", user_cfg) == "claude-3-5-sonnet-latest"
    assert _get_default_model("DEFAULT_FAST_MODEL", user_cfg) == "claude-3-5-haiku-latest"


def test_explicit_user_default_models_override():
    """User's explicit default_models settings in config.json always win."""
    user_cfg = {
        "api_keys": {"openai": "sk-user-key"},
        "default_models": {
            "DEFAULT_SMART_MODEL": "openrouter/deepseek/deepseek-r1",
            "DEFAULT_CODER_MODEL": "openrouter/qwen/qwen-2.5-coder-32b-instruct",
            "DEFAULT_FAST_MODEL": "openrouter/meta-llama/llama-3.1-8b-instruct",
            "DEFAULT_JUDGE_MODEL": "openrouter/free",
            "DEFAULT_EMBEDDING_MODEL": "ollama/nomic-embed-text"
        }
    }

    assert _get_default_model("DEFAULT_SMART_MODEL", user_cfg) == "openrouter/deepseek/deepseek-r1"
    assert _get_default_model("DEFAULT_CODER_MODEL", user_cfg) == "openrouter/qwen/qwen-2.5-coder-32b-instruct"
    assert _get_default_model("DEFAULT_FAST_MODEL", user_cfg) == "openrouter/meta-llama/llama-3.1-8b-instruct"
    assert _get_default_model("DEFAULT_JUDGE_MODEL", user_cfg) == "openrouter/free"
    assert _get_default_model("DEFAULT_EMBEDDING_MODEL", user_cfg) == "ollama/nomic-embed-text"


def test_hardcoded_fallback_when_no_keys_at_all(monkeypatch):
    """When zero keys exist in cfg and no host env vars exist, guaranteed hardcoded fallbacks are returned."""
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    empty_cfg = {"api_keys": {}, "default_models": {}}

    assert _get_default_model("DEFAULT_SMART_MODEL", empty_cfg) == "openrouter/auto"
    assert _get_default_model("DEFAULT_CODER_MODEL", empty_cfg) == "openrouter/free"
    assert _get_default_model("DEFAULT_FAST_MODEL", empty_cfg) == "openrouter/free"
    assert _get_default_model("DEFAULT_JUDGE_MODEL", empty_cfg) == "openrouter/free"
    assert _get_default_model("DEFAULT_EMBEDDING_MODEL", empty_cfg) == "auto"


def test_dynamic_agent_settings():
    """Agent runtime settings are dynamically resolved from config.json."""
    custom_cfg = {
        "agent_settings": {
            "MAX_LOOPS": 42,
            "APPROVAL_TIMEOUT_SECS": 120,
            "MAX_QUEUE_SIZE": 1000,
            "DREAM_INTERVAL_MINUTES": 30,
            "MEMORY_RETRIEVAL_LIMIT": 10,
            "CONTEXT_COMPACTION_THRESHOLD": 25,
        }
    }

    with patch("core.llm.config_manager.load_config", return_value=custom_cfg):
        assert core.config.MAX_LOOPS == 42
        assert core.config.APPROVAL_TIMEOUT_SECS == 120
        assert core.config.MAX_QUEUE_SIZE == 1000
        assert core.config.DREAM_INTERVAL_MINUTES == 30
        assert core.config.MEMORY_RETRIEVAL_LIMIT == 10
        assert core.config.CONTEXT_COMPACTION_THRESHOLD == 25
