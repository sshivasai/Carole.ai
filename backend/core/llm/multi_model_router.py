"""
# backend/core/llm/multi_model_router.py

This module acts as the gateway to route LLM requests to different providers.

Supported Providers:
1. Anthropic  (claude-* models)
2. OpenAI     (gpt-*, o4-*, o3-* models)
3. Google     (gemini-* models)
4. OpenRouter (openrouter/free | openrouter/auto | openrouter/<vendor>/<model>)
5. NVIDIA NIM (nvidia/<model>)
6. Ollama     (ollama/<model>  — local)

Special OpenRouter modes:
- openrouter/free : Randomly selects a free model; reasoning enabled.
- openrouter/auto : NotDiamond auto-router selects best model per prompt.

Features:
- MODEL_CATALOG — single source of truth for all providers and models.
- generate_stream_with_fallback() — automatic per-agent fallback on error.
- Standard generation completions.
- Asynchronous generator streaming (live-stream to WebSocket EventBus).
- Dynamic base-URL for local Ollama endpoints.
- Gemini embeddings fallback when OpenAI key is unavailable.
- Retry with exponential backoff for transient API failures.
"""

import os
import re
import json
import asyncio
import logging
from decimal import Decimal, ROUND_HALF_UP
import random
import httpx
from contextlib import aclosing
from urllib.parse import urlparse
from typing import AsyncGenerator, List, Dict, Optional, Any
from core.llm.config_manager import load_config, get_key, has_user_configured_keys

logger = logging.getLogger("carole.router")


# ── BYOK Error Classification ─────────────────────────────────────────────────
# Structured error types for provider failures. The agent loop and frontend
# use these to display actionable warnings instead of raw technical strings.

ERROR_MISSING_KEY      = "missing_api_key"
ERROR_INVALID_KEY      = "invalid_api_key"
ERROR_INSUFFICIENT     = "insufficient_quota"
ERROR_RATE_LIMITED     = "rate_limit_exceeded"
ERROR_MODEL_NOT_FOUND  = "model_not_found"
ERROR_PROVIDER_DOWN    = "provider_unavailable"

# Human-readable action hints per error type
_ACTION_HINTS = {
    ERROR_MISSING_KEY:     "Open Settings → API Keys and add your {provider} key.",
    ERROR_INVALID_KEY:     "Your {provider} API key appears to be invalid or revoked. Check Settings → API Keys.",
    ERROR_INSUFFICIENT:    "Your {provider} account has insufficient credits or quota. Top up your balance or switch to a free model.",
    ERROR_RATE_LIMITED:    "Rate limit exceeded for {provider}. Wait a moment or switch to another model.",
    ERROR_MODEL_NOT_FOUND: "Model '{model}' is not available on {provider}. It may require a higher-tier account or may not exist.",
    ERROR_PROVIDER_DOWN:   "{provider} is temporarily unreachable. Try again later or switch providers.",
}

# Provider display names
_PROVIDER_DISPLAY = {
    "openai": "OpenAI", "anthropic": "Anthropic", "google": "Google Gemini",
    "openrouter": "OpenRouter", "nvidia": "NVIDIA", "ollama": "Ollama",
}

# Map URL patterns to (provider_key, missing_env_var_name)
_URL_PROVIDER_MAP = {
    "api.openai.com":            ("openai",     "OPENAI_API_KEY"),
    "openrouter.ai":             ("openrouter", "OPENROUTER_API_KEY"),
    "integrate.api.nvidia.com":  ("nvidia",     "NVIDIA_API_KEY"),
    "generativelanguage.googleapis.com": ("google", "GOOGLE_API_KEY"),
    "api.anthropic.com":         ("anthropic",  "ANTHROPIC_API_KEY"),
}


def _provider_from_url(url: str) -> tuple[str, str]:
    hostname = (urlparse(url).hostname or "").lower()
    return _URL_PROVIDER_MAP.get(hostname, ("unknown", ""))


def _anthropic_thinking_budget(effort: Optional[str], max_tokens: int) -> Optional[int]:
    budgets = {"low": 1024, "medium": 4096, "high": 8192}
    if not effort or effort == "none":
        return None
    if effort not in budgets:
        raise ValueError("reasoning_effort must be none, low, medium, or high")
    if max_tokens <= 1024:
        raise ValueError("Anthropic extended thinking requires max_tokens > 1024")
    # Do not silently increase the caller's output/context budget.
    return min(budgets[effort], max_tokens - 1)


class LLMProviderError(Exception):
    """Structured exception for LLM provider failures.

    Attributes:
        error_type: One of ERROR_* constants (missing_api_key, invalid_api_key, etc.)
        provider:   Provider key string (openai, anthropic, google, etc.)
        model:      Model string that was requested.
        message:    Human-readable description of the error.
        status_code: HTTP status code if applicable (401, 402, 429, etc.)
        action_hint: Actionable suggestion for the user.
        env_key_name: Environment variable name for the missing key (e.g. OPENAI_API_KEY).
    """

    def __init__(
        self,
        error_type: str,
        provider: str,
        model: str = "",
        message: str = "",
        status_code: int | None = None,
        env_key_name: str = "",
    ):
        self.error_type = error_type
        self.provider = provider
        self.model = model
        self.status_code = status_code
        self.env_key_name = env_key_name

        provider_display = _PROVIDER_DISPLAY.get(provider, provider.title())
        self.message = message or _ACTION_HINTS.get(error_type, "An error occurred with {provider}.").format(
            provider=provider_display, model=model
        )
        self.action_hint = _ACTION_HINTS.get(error_type, "").format(
            provider=provider_display, model=model
        )
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Serialize for EventBus / WebSocket transmission."""
        return {
            "error_type": self.error_type,
            "provider": self.provider,
            "model": self.model,
            "message": self.message,
            "status_code": self.status_code,
            "action_hint": self.action_hint,
            "env_key_name": self.env_key_name,
        }

    @staticmethod
    def classify_http_error(status_code: int, body: str, provider: str, model: str = "") -> "LLMProviderError":
        """Classify an HTTP error response into a structured LLMProviderError."""
        body_lower = body.lower()

        if status_code in (401, 403):
            return LLMProviderError(ERROR_INVALID_KEY, provider, model, status_code=status_code)

        if status_code == 402 or any(kw in body_lower for kw in (
            "insufficient_quota", "credit", "balance", "billing", "payment_required",
            "exceeded your current quota",
        )):
            return LLMProviderError(ERROR_INSUFFICIENT, provider, model, status_code=status_code)

        if status_code == 429:
            return LLMProviderError(ERROR_RATE_LIMITED, provider, model, status_code=status_code)

        if status_code == 404 or "model_not_found" in body_lower or "does not exist" in body_lower:
            return LLMProviderError(ERROR_MODEL_NOT_FOUND, provider, model, status_code=status_code)

        if status_code >= 500:
            return LLMProviderError(
                ERROR_PROVIDER_DOWN, provider, model,
                message=f"{_PROVIDER_DISPLAY.get(provider, provider)} returned server error {status_code}.",
                status_code=status_code,
            )

        # Fallback for unknown error codes
        return LLMProviderError(
            ERROR_PROVIDER_DOWN, provider, model,
            message=f"{_PROVIDER_DISPLAY.get(provider, provider)} returned HTTP {status_code}: {body[:200]}",
            status_code=status_code,
        )

def get_model_context_window(model: str) -> int:
    """Returns the approximate context window limit in tokens for a given model string."""
    m = (model or "").lower()
    if "gemini" in m:
        return 1_000_000
    if "claude" in m:
        return 200_000
    if "gpt-4" in m or "o4" in m or "o3" in m or "llama-3" in m or "deepseek" in m or "qwen" in m or "mistral-large" in m:
        return 128_000
    if "gpt-3.5" in m or "phi" in m or "16k" in m:
        return 16_384
    if "32k" in m or "mistral" in m:
        return 32_768
    if "8k" in m:
        return 8_192
    if "4k" in m:
        return 4_096
    if "free" in m or "auto" in m:
        return 128_000
    return 65_536


def clamp_context_for_model(
    model: str,
    system_prompt: str,
    messages: List[Dict[str, Any]],
    requested_max_tokens: int = 4000,
) -> tuple[str, List[Dict[str, Any]], int]:
    """
    Ensures (estimated_input_tokens + max_tokens) <= model_context_window.
    If input tokens alone exceed or approach the limit, truncates/compacts
    older messages and system prompt sections, and scales down max_tokens.
    """
    if requested_max_tokens < 1:
        raise ValueError("requested_max_tokens must be positive")
    ctx_limit = get_model_context_window(model)

    def _msg_chars(msg_list):
        total = 0
        for m in msg_list:
            c = m.get("content", "")
            if isinstance(c, str):
                total += len(c)
            elif isinstance(c, list):
                total += sum(len(str(i.get("text", ""))) for i in c if isinstance(i, dict))
        return total

    # Reserve at least 256 tokens for output, up to requested_max_tokens
    min_output_tokens = min(256, requested_max_tokens)
    target_input_token_limit = max(1000, ctx_limit - min_output_tokens - 100)

    current_input_chars = len(system_prompt) + _msg_chars(messages)
    current_input_tokens = current_input_chars // 4

    # 1. Truncate intermediate messages if input exceeds budget
    trimmed_messages = list(messages)
    if current_input_tokens > target_input_token_limit and len(trimmed_messages) > 1:
        while len(trimmed_messages) > 1:
            chars = len(system_prompt) + _msg_chars(trimmed_messages)
            if chars // 4 <= target_input_token_limit:
                break
            trimmed_messages.pop(0)
        current_input_chars = len(system_prompt) + _msg_chars(trimmed_messages)
        current_input_tokens = current_input_chars // 4

    # 2. Trim the system prompt, including the truncation marker in the budget.
    trimmed_system_prompt = system_prompt
    if current_input_tokens > target_input_token_limit:
        msg_chars = _msg_chars(trimmed_messages)
        max_sys_chars = max(0, target_input_token_limit * 4 - msg_chars)
        if len(trimmed_system_prompt) > max_sys_chars:
            marker = "\n\n[System prompt truncated to fit model context limit]"
            if max_sys_chars >= len(marker):
                trimmed_system_prompt = (
                    trimmed_system_prompt[:max_sys_chars - len(marker)] + marker
                )
            else:
                trimmed_system_prompt = trimmed_system_prompt[:max_sys_chars]
            current_input_chars = len(trimmed_system_prompt) + msg_chars
            current_input_tokens = (current_input_chars + 3) // 4

    # A single oversized message cannot be made safe by trimming the system prompt.
    if current_input_tokens > target_input_token_limit:
        raise ValueError(
            f"Input exceeds the estimated context budget for {model!r}; "
            "split or compact the remaining message before retrying."
        )

    # This is a text-length estimate, not a tokenizer/multimodal guarantee.
    available_tokens = ctx_limit - current_input_tokens - 50
    if available_tokens < 1:
        raise ValueError(f"No output-token budget remains for {model!r}")
    safe_max_tokens = min(requested_max_tokens, available_tokens)

    return trimmed_system_prompt, trimmed_messages, safe_max_tokens


class MultiModelRouter:
    def __init__(self):
        # FIX H3: Shared persistent httpx client with connection pooling.
        # Previously each LLM call opened a new TCP connection (100-300ms overhead).
        # A persistent client reuses connections via HTTP keep-alive, dramatically
        # reducing per-request latency.
        #   - max_connections=50: enough for concurrent multi-agent workloads
        #   - max_keepalive_connections=20: keep warm connections for most-used providers
        #   - keepalive_expiry=30s: close idle connections before server-side timeout
        self._http_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=20,
                keepalive_expiry=30.0,
            ),
            timeout=httpx.Timeout(
                connect=10.0,    # TCP connect
                read=300.0,      # streaming read (long for slow models)
                write=30.0,
                pool=5.0,
            ),
            http2=True,          # Enable HTTP/2 where supported (Anthropic, OpenAI)
        )
        self.reload_config()

    async def aclose(self) -> None:
        """Close the shared HTTP client. Call on application shutdown."""
        await self._http_client.aclose()

    def reload_config(self) -> None:
        """
        Loads (or re-loads) API keys from ~/.carole/config.json with env var fallback.
        Call this after saving new settings to hot-reload without a server restart.
        """
        cfg = load_config()
        self.anthropic_key = get_key(cfg, "anthropic", "ANTHROPIC_API_KEY")
        self.openai_key    = get_key(cfg, "openai",    "OPENAI_API_KEY")
        self.gemini_key    = get_key(cfg, "google",    "GOOGLE_API_KEY")
        self.openrouter_key = get_key(cfg, "openrouter", "OPENROUTER_API_KEY")
        cfg_ollama = cfg.get("providers", {}).get("ollama_base_url", "").strip()
        if cfg_ollama:
            self.ollama_base_url = cfg_ollama
        elif not has_user_configured_keys(cfg):
            self.ollama_base_url = (
                os.getenv("OLLAMA_BASE_URL", "").strip()
                or os.getenv("OLLAMA_HOST", "").strip()
                or "http://localhost:11434/v1"
            )
        else:
            self.ollama_base_url = "http://localhost:11434/v1"

    async def generate_completion(
        self,
        model: str,
        system_prompt: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        project_id: Optional[str] = None,
        team_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        reasoning_effort: str = "none",
    ) -> str:
        """
        Generates a standard non-streaming text completion.
        """
        response_text = ""
        async for chunk in self.generate_stream(
            model, system_prompt, messages, temperature, max_tokens,
            project_id, team_id, agent_id, agent_name,
            reasoning_effort=reasoning_effort,
        ):
            response_text += chunk
        return response_text

    async def generate_stream_with_fallback(
        self,
        model: str,
        system_prompt: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        project_id: Optional[str] = None,
        team_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        fallback_model: Optional[str] = None,
        reasoning_effort: str = "none",
    ) -> AsyncGenerator[str, None]:
        """
        Streams the primary model. If the stream starts with a router error,
        automatically falls back to fallback_model (if configured).
        Emits a visible ⚠️ warning chunk before retrying.
        """
        # --- Budget Enforcement (API-08) ---
        # Check if the project has a budget limit set and whether it has been exceeded.
        # This runs before every LLM call to prevent silent overspending.
        if project_id:
            try:
                from core.memory.database import async_session
                from core.memory.models import Project
                from sqlalchemy import select
                import uuid as _uuid
                async with async_session() as _db:
                    proj = (await _db.execute(
                        select(Project).where(Project.id == _uuid.UUID(project_id))
                    )).scalar_one_or_none()
                    if proj and proj.budget_limit_usd is not None:
                        limit = float(proj.budget_limit_usd)
                        spent = float(proj.total_spend_usd or 0)
                        if spent >= limit:
                            msg = (
                                f"🚫 **Budget limit reached** — this project has a ${limit:.2f} budget "
                                f"and has spent ${spent:.4f}. LLM calls are blocked. "
                                f"Raise the budget in Project Settings to continue."
                            )
                            logger.warning("Budget exceeded for project %s (%.4f / %.2f)", project_id, spent, limit)
                            yield msg
                            return
            except Exception as _be:
                logger.debug("Budget check skipped due to error: %s", _be)

        primary_yielded_content = False

        primary = self.generate_stream(
            model, system_prompt, messages, temperature, max_tokens,
            project_id, team_id, agent_id, agent_name,
            reasoning_effort=reasoning_effort,
        )
        try:
            async with aclosing(primary):
                async for chunk in primary:
                    if chunk:
                        primary_yielded_content = True
                    yield chunk
            return
        except LLMProviderError:
            fallback = (fallback_model or "").strip()
            if primary_yielded_content or not fallback or fallback == model:
                raise
            logger.warning("Primary model %s failed; falling back to %s", model, fallback)

        # Keep diagnostics out of generated model content.
        secondary = self.generate_stream(
            fallback, system_prompt, messages, temperature, max_tokens,
            project_id, team_id, agent_id, agent_name,
            reasoning_effort=reasoning_effort,
        )
        async with aclosing(secondary):
            async for chunk in secondary:
                yield chunk


    async def generate_stream(
        self,
        model: str,
        system_prompt: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        project_id: Optional[str] = None,
        team_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        reasoning_effort: str = "none",
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronous generator streaming chunks of the completion in real-time.
        Routes to the correct provider based on model name prefix.
        Tracks token usage upon completion.
        """
        response_text = ""
        provider = "unknown"

        # ── Clamp context & max_tokens to prevent 400 Context Length Exceeded ──
        system_prompt, messages, max_tokens = clamp_context_for_model(
            model, system_prompt, messages, max_tokens
        )

        # ── Build reasoning extra_body for OpenAI-compatible endpoints ──────────
        # Anthropic uses a different mechanism (_stream_anthropic handles it).
        # OpenRouter uses { reasoning: { effort: "low"|"medium"|"high" } }
        # OpenAI o-series uses { reasoning_effort: "low"|"medium"|"high" }
        _effort = reasoning_effort if reasoning_effort and reasoning_effort != "none" else None

        try:
            if model.startswith("openrouter/"):
                provider = "openrouter"
                # openrouter/free and /auto always get reasoning enabled; other models
                # respect the per-agent reasoning_effort setting.
                use_special = model in ("openrouter/free", "openrouter/auto")
                if use_special:
                    extra = {"reasoning": {"enabled": True}}
                    target_model = model  # /free and /auto are OpenRouter meta-routes, keep as-is
                else:
                    if _effort:
                        extra = {"reasoning": {"effort": _effort}}
                    else:
                        extra = None
                    # Strip the "openrouter/" prefix — the raw vendor/model goes to the API
                    target_model = model[len("openrouter/"):]
                async for chunk in self._stream_openai_compatible(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    key=self.openrouter_key,
                    model=target_model,
                    system_prompt=system_prompt,
                    messages=messages,
                    temp=temperature,
                    max_tokens=max_tokens,
                    extra_body=extra,
                ):
                    response_text += chunk
                    yield chunk

            elif model.startswith("nvidia/"):
                provider = "nvidia"
                target_model = model.replace("nvidia/", "", 1)
                async for chunk in self._stream_openai_compatible(
                    url="https://integrate.api.nvidia.com/v1/chat/completions",
                    key=self.nvidia_key,
                    model=target_model,
                    system_prompt=system_prompt,
                    messages=messages,
                    temp=temperature,
                    max_tokens=max_tokens,
                ):
                    response_text += chunk
                    yield chunk

            elif model.startswith("ollama/"):
                provider = "ollama"
                target_model = model.replace("ollama/", "", 1)
                async for chunk in self._stream_openai_compatible(
                    url=f"{self.ollama_base_url}/chat/completions",
                    key=None,
                    model=target_model,
                    system_prompt=system_prompt,
                    messages=messages,
                    temp=temperature,
                    max_tokens=max_tokens,
                ):
                    response_text += chunk
                    yield chunk

            elif model.startswith("gemini"):
                provider = "google"
                async for chunk in self._stream_gemini(model, system_prompt, messages, temperature, max_tokens):
                    response_text += chunk
                    yield chunk

            elif model.startswith("claude"):
                if self.anthropic_key:
                    provider = "anthropic"
                    async for chunk in self._stream_anthropic(
                        model, system_prompt, messages, temperature, max_tokens,
                        reasoning_effort=_effort,
                    ):
                        response_text += chunk
                        yield chunk
                elif self.openrouter_key:
                    provider = "openrouter"
                    target_model = f"anthropic/{model}" if "/" not in model else model
                    target_model = target_model.replace("claude-3-5-sonnet", "claude-3.5-sonnet")
                    target_model = target_model.replace("-20241022", "")
                    extra = {"reasoning": {"effort": _effort}} if _effort else None
                    async for chunk in self._stream_openai_compatible(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        key=self.openrouter_key,
                        model=target_model,
                        system_prompt=system_prompt,
                        messages=messages,
                        temp=temperature,
                        max_tokens=max_tokens,
                        extra_body=extra,
                    ):
                        response_text += chunk
                        yield chunk
                else:
                    provider = "anthropic"
                    async for chunk in self._stream_anthropic(
                        model, system_prompt, messages, temperature, max_tokens,
                        reasoning_effort=_effort,
                    ):
                        response_text += chunk
                        yield chunk

            else:
                # gpt-*, o3-*, o4-*, or any other model
                if self.openai_key:
                    provider = "openai"
                    # OpenAI reasoning models (o-series) accept reasoning_effort
                    _is_o_series = any(model.startswith(p) for p in ("o1", "o3", "o4"))
                    extra = {"reasoning_effort": _effort} if _effort and _is_o_series else None
                    async for chunk in self._stream_openai_compatible(
                        url="https://api.openai.com/v1/chat/completions",
                        key=self.openai_key,
                        model=model,
                        system_prompt=system_prompt,
                        messages=messages,
                        temp=temperature,
                        max_tokens=max_tokens,
                        extra_body=extra,
                    ):
                        response_text += chunk
                        yield chunk
                elif self.openrouter_key:
                    provider = "openrouter"
                    target_model = f"openai/{model}" if "/" not in model else model
                    extra = {"reasoning": {"effort": _effort}} if _effort else None
                    async for chunk in self._stream_openai_compatible(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        key=self.openrouter_key,
                        model=target_model,
                        system_prompt=system_prompt,
                        messages=messages,
                        temp=temperature,
                        max_tokens=max_tokens,
                        extra_body=extra,
                    ):
                        response_text += chunk
                        yield chunk
                else:
                    provider = "openai"
                    async for chunk in self._stream_openai_compatible(
                        url="https://api.openai.com/v1/chat/completions",
                        key=self.openai_key,
                        model=model,
                        system_prompt=system_prompt,
                        messages=messages,
                        temp=temperature,
                        max_tokens=max_tokens,
                    ):
                        response_text += chunk
                        yield chunk
        finally:
            if project_id or team_id or agent_id:
                asyncio.create_task(
                    self._log_usage(
                        provider=provider,
                        model=model,
                        system_prompt=system_prompt,
                        messages=messages,
                        response_text=response_text,
                        project_id=project_id,
                        team_id=team_id,
                        agent_id=agent_id,
                        agent_name=agent_name
                    )
                )

    async def _stream_openai_compatible(
        self,
        url: str,
        key: Optional[str],
        model: str,
        system_prompt: str,
        messages: List[Dict[str, str]],
        temp: float,
        max_tokens: int,
        extra_body: Optional[dict] = None,
    ) -> AsyncGenerator[str, None]:
        if "api.openai.com" in url and not key:
            raise LLMProviderError(ERROR_MISSING_KEY, "openai", model, env_key_name="OPENAI_API_KEY")
        if "openrouter.ai" in url and not key:
            raise LLMProviderError(ERROR_MISSING_KEY, "openrouter", model, env_key_name="OPENROUTER_API_KEY")
        if "integrate.api.nvidia.com" in url and not key:
            raise LLMProviderError(ERROR_MISSING_KEY, "nvidia", model, env_key_name="NVIDIA_API_KEY")

        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"

        formatted_messages = self._format_messages_for_provider(messages, "openai")
        final_messages = [{"role": "system", "content": system_prompt}] + formatted_messages

        payload: dict = {
            "model": model,
            "messages": final_messages,
            "temperature": temp,
            "max_tokens": max_tokens,
            "stream": True,
        }
        # Merge any extra body params (e.g. reasoning for openrouter/free & /auto)
        if extra_body:
            payload.update(extra_body)

        async for chunk in self._stream_with_retry(url, headers, payload, "openai"):
            yield chunk

    async def _log_usage(
        self,
        provider: str,
        model: str,
        system_prompt: str,
        messages: List[Dict[str, str]],
        response_text: str,
        project_id: Optional[str],
        team_id: Optional[str],
        agent_id: Optional[str],
        agent_name: Optional[str]
    ):
        try:
            def _get_len(c):
                if isinstance(c, str):
                    return len(c)
                elif isinstance(c, list):
                    return sum(len(str(item)) for item in c)
                return 0

            prompt_chars = len(system_prompt) + sum(_get_len(m.get("content", "")) for m in messages)
            prompt_tokens = int(prompt_chars / 4)
            completion_tokens = int(len(response_text) / 4)
            total_tokens = prompt_tokens + completion_tokens

            # Pricing mappings (per 1M tokens)
            pricing = {
                "gpt-4o-mini": (0.15, 0.60),
                "openai/gpt-4o-mini": (0.15, 0.60),
                "gpt-4o": (2.50, 10.00),
                "openai/gpt-4o": (2.50, 10.00),
                "o4-mini": (1.15, 4.50),
                "claude-sonnet-4": (3.00, 15.00),
                "claude-opus-4": (15.00, 75.00),
                "claude-3-5-sonnet-20241022": (3.00, 15.00),
                "gemini-2.0-flash": (0.075, 0.30),
                "gemini-2.5-pro": (1.25, 5.00),
                "anthropic/claude-3.5-sonnet": (3.00, 15.00),
            }

            clean_model = model.replace("openrouter/", "", 1) if model.startswith("openrouter/") else model
            rate_in, rate_out = pricing.get(clean_model, pricing.get(model, (0.0, 0.0)))
            if "free" in model.lower() and provider in ["openrouter", "nvidia", "ollama"]:
                rate_in, rate_out = 0.0, 0.0

            cost = (
                (
                    Decimal(prompt_tokens) * Decimal(str(rate_in))
                    + Decimal(completion_tokens) * Decimal(str(rate_out))
                )
                / Decimal("1000000")
            ).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

            from core.memory.database import async_session
            from core.memory.models import TokenUsage, Project
            from sqlalchemy import update
            import uuid

            async with async_session() as session:
                usage = TokenUsage(
                    project_id=uuid.UUID(project_id) if isinstance(project_id, str) else project_id,
                    team_id=uuid.UUID(team_id) if isinstance(team_id, str) else team_id,
                    agent_id=uuid.UUID(agent_id) if isinstance(agent_id, str) else agent_id,
                    agent_name=agent_name,
                    model=model,
                    provider=provider,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    estimated_cost_usd=cost
                )
                session.add(usage)
                
                # Update Project total spend
                if project_id:
                    proj_uuid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
                    # Atomic increment, committed in the same transaction as usage.
                    await session.execute(
                        update(Project)
                        .where(Project.id == proj_uuid)
                        .values(total_spend_usd=Project.total_spend_usd + cost)
                    )
                
                await session.commit()

            # Broadcast real-time token and cost stats to UI
            if team_id:
                try:
                    from core.chat.event_bus import event_bus
                    await event_bus.publish(f"team:{team_id}", {
                        "type": "token_usage",
                        "agent_id": str(agent_id) if agent_id else None,
                        "agent_name": agent_name,
                        "model": model,
                        "provider": provider,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                        "estimated_cost_usd": f"{cost:.8f}",
                    })
                except Exception:
                    pass
        except Exception as e:
            import logging as _logging
            _logging.getLogger("carole.router").warning("Token usage tracking failed: %s", e)

    # ================================================================
    # Anthropic (Claude)
    # ================================================================

    async def _stream_anthropic(
        self, model: str, system_prompt: str, messages: List[Dict[str, str]],
        temp: float, max_tokens: int,
        reasoning_effort: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        if not self.anthropic_key:
            raise LLMProviderError(ERROR_MISSING_KEY, "anthropic", model, env_key_name="ANTHROPIC_API_KEY")

        headers = {
            "x-api-key": self.anthropic_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        # Map reasoning effort levels to Anthropic budget_tokens
        _ANTHROPIC_BUDGETS = {"low": 1024, "medium": 4096, "high": 8192}

        formatted_messages = self._format_messages_for_provider(messages, "anthropic")

        # Enable Anthropic Prompt Caching for system instructions > 1024 chars
        if len(system_prompt) > 1024:
            system_payload: Any = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }
            ]
        else:
            system_payload = system_prompt

        payload: dict = {
            "model": model,
            "system": system_payload,
            "messages": formatted_messages,
            "max_tokens": max_tokens,
            "stream": True,
        }

        thinking_budget = _anthropic_thinking_budget(reasoning_effort, max_tokens)
        if thinking_budget is not None:
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }
            payload["temperature"] = 1
        else:
            payload["temperature"] = temp

        async for chunk in self._stream_with_retry("https://api.anthropic.com/v1/messages", headers, payload, "anthropic"):
            yield chunk


    # ================================================================
    # Google Gemini
    # ================================================================

    async def _stream_gemini(
        self, model: str, system_prompt: str, messages: List[Dict[str, str]], temp: float, max_tokens: int
    ) -> AsyncGenerator[str, None]:
        if not self.gemini_key:
            raise LLMProviderError(ERROR_MISSING_KEY, "google", model, env_key_name="GOOGLE_API_KEY")

        # Build Gemini-format contents array
        contents = self._format_messages_for_provider(messages, "google")

        payload = {
            "contents": contents,
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "generationConfig": {
                "temperature": temp,
                "maxOutputTokens": max_tokens,
            }
        }

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
            f":streamGenerateContent?alt=sse&key={self.gemini_key}"
        )

        try:
            async with self._http_client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    err_body = await response.aread()
                    raise LLMProviderError.classify_http_error(response.status_code, err_body.decode('utf-8'), "google", model)

                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        try:
                            data = json.loads(data_str)
                            candidates = data.get("candidates", [])
                            if candidates:
                                content = candidates[0].get("content", {})
                                parts = content.get("parts", [])
                                for part in parts:
                                    text = part.get("text", "")
                                    if text:
                                        yield text
                        except json.JSONDecodeError:
                            continue
        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(ERROR_PROVIDER_DOWN, "google", model, message=f"Router Connection Exception (Gemini): {str(e)}")

    # ================================================================
    # Shared SSE streaming with retry
    # ================================================================

    @staticmethod
    async def _iter_sse_payloads(response: httpx.Response) -> AsyncGenerator[str, None]:
        """Parse complete SSE events, including multiline data fields."""
        data_lines: list[str] = []
        event_chars = 0
        max_event_chars = 4 * 1024 * 1024

        async for line in response.aiter_lines():
            if line == "":
                if data_lines:
                    yield "\n".join(data_lines)
                data_lines = []
                event_chars = 0
                continue

            if line.startswith(":"):
                continue

            field, separator, value = line.partition(":")
            if field != "data":
                continue

            if separator and value.startswith(" "):
                value = value[1:]

            event_chars += len(value)
            if event_chars > max_event_chars:
                raise ValueError("SSE event exceeded the maximum supported size")
            data_lines.append(value)

        # Do not dispatch an incomplete final event. The caller verifies that
        # the stream received its provider-specific terminal event.

    @staticmethod
    def _sse_error(
        data: dict,
        provider: str,
        model: str,
    ) -> Optional[LLMProviderError]:
        error = data.get("error")
        if error is None and data.get("type") != "error":
            return None

        if not isinstance(error, dict):
            return LLMProviderError(ERROR_PROVIDER_DOWN, provider, model)

        code = error.get("code")
        if isinstance(code, str) and code.isdigit():
            code = int(code)

        if isinstance(code, int) and 400 <= code <= 599:
            return LLMProviderError.classify_http_error(
                code, json.dumps(error), provider, model
            )

        error_type = str(error.get("type") or code or "").lower()
        classification = {
            "authentication_error": ERROR_INVALID_KEY,
            "invalid_api_key": ERROR_INVALID_KEY,
            "permission_error": ERROR_INVALID_KEY,
            "rate_limit_error": ERROR_RATE_LIMITED,
            "rate_limit_exceeded": ERROR_RATE_LIMITED,
            "insufficient_quota": ERROR_INSUFFICIENT,
            "not_found_error": ERROR_MODEL_NOT_FOUND,
            "model_not_found": ERROR_MODEL_NOT_FOUND,
            "overloaded_error": ERROR_PROVIDER_DOWN,
            "api_error": ERROR_PROVIDER_DOWN,
        }.get(error_type, ERROR_PROVIDER_DOWN)

        return LLMProviderError(classification, provider, model)

    async def _stream_with_retry(
        self,
        url: str,
        headers: dict,
        payload: dict,
        parse_format: str,
        max_retries: int = 3,
    ) -> AsyncGenerator[str, None]:
        stream = self._stream_with_retry_rich(
            url, headers, payload, parse_format, max_retries
        )
        async with aclosing(stream):
            async for chunk in stream:
                if chunk["content"]:
                    yield chunk["content"]

    async def _stream_with_retry_rich(
        self,
        url: str,
        headers: dict,
        payload: dict,
        parse_format: str,
        max_retries: int = 3,
    ) -> AsyncGenerator[dict[str, str], None]:
        """Retry transient failures only before any output has been emitted."""
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")

        provider, env_key_name = _provider_from_url(url)
        model = str(payload.get("model", ""))
        emitted = False

        normalized_headers = {k.lower(): v for k, v in headers.items()}
        if env_key_name:
            auth_header = "x-api-key" if provider == "anthropic" else "authorization"
            if not normalized_headers.get(auth_header):
                raise LLMProviderError(
                    ERROR_MISSING_KEY,
                    provider,
                    model,
                    env_key_name=env_key_name,
                )

        for attempt in range(max_retries):
            retry_after: Optional[float] = None

            try:
                async with self._http_client.stream(
                    "POST", url, headers=headers, json=payload
                ) as response:
                    if response.status_code != 200:
                        body = (await response.aread()).decode("utf-8", errors="replace")

                        raw_retry_after = response.headers.get("Retry-After")
                        if raw_retry_after:
                            try:
                                retry_after = max(
                                    0.0, min(float(raw_retry_after), 120.0)
                                )
                            except ValueError:
                                pass

                        raise LLMProviderError.classify_http_error(
                            response.status_code, body, provider, model
                        )

                    terminated = False
                    async for raw in self._iter_sse_payloads(response):
                        if raw.strip() == "[DONE]":
                            terminated = True
                            break
                        if not raw.strip():
                            continue

                        data = json.loads(raw)
                        if not isinstance(data, dict):
                            raise ValueError("Expected an SSE JSON object")

                        error = self._sse_error(data, provider, model)
                        if error is not None:
                            raise error

                        if (
                            parse_format == "anthropic"
                            and data.get("type") == "message_stop"
                        ):
                            terminated = True
                            break

                        content, reasoning = self._extract_text_from_sse(
                            data, parse_format
                        )
                        if content or reasoning:
                            emitted = True
                            yield {"content": content, "reasoning": reasoning}

                    if not terminated:
                        raise LLMProviderError(
                            ERROR_PROVIDER_DOWN,
                            provider,
                            model,
                            message="Provider stream ended without a completion marker.",
                        )
                    return

            except LLMProviderError as exc:
                retryable = (
                    exc.error_type == ERROR_RATE_LIMITED
                    or (
                        exc.error_type == ERROR_PROVIDER_DOWN
                        and (
                            exc.status_code is None
                            or exc.status_code >= 500
                        )
                    )
                )
                if emitted or not retryable or attempt == max_retries - 1:
                    raise

            except httpx.TransportError as exc:
                if emitted or attempt == max_retries - 1:
                    raise LLMProviderError(
                        ERROR_PROVIDER_DOWN,
                        provider,
                        model,
                        message=f"Provider connection failed ({type(exc).__name__}).",
                    ) from exc

            except (ValueError, TypeError, KeyError) as exc:
                # Malformed protocol data is not a successful completion.
                raise LLMProviderError(
                    ERROR_PROVIDER_DOWN,
                    provider,
                    model,
                    message="Provider returned an invalid streaming response.",
                ) from exc

            # The response context is closed before sleeping.
            delay = (
                retry_after
                if retry_after is not None
                else min(2 ** attempt, 30) + random.uniform(0, 0.5)
            )
            logger.warning(
                "%s request failed before output; retrying in %.2fs (%d/%d)",
                provider,
                delay,
                attempt + 1,
                max_retries,
            )
            await asyncio.sleep(delay)


    @staticmethod
    def _extract_text_from_sse(data: dict, parse_format: str) -> tuple[str, str]:
        """Extracts (content, reasoning) from an SSE data payload."""
        content = ""
        reasoning = ""
        if parse_format == "anthropic":
            event_type = data.get("type", "")
            if event_type == "content_block_delta":
                delta = data.get("delta", {})
                dtype = delta.get("type", "")
                if dtype == "text_delta":
                    content = delta.get("text", "")
                elif dtype == "thinking_delta":
                    reasoning = delta.get("thinking", "")
        elif parse_format == "openai":
            choices = data.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content", "") or ""
                # OpenRouter / DeepSeek R1 / o-series reasoning
                reasoning = delta.get("reasoning_content", "") or delta.get("reasoning", "") or ""
        return content, reasoning

    # ================================================================
    # Native Tool Calling (all providers)
    # ================================================================

    async def generate_with_tools(
        self,
        model: str,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        temperature: float = 0.4,
        max_tokens: int = 8192,
        tool_choice: str = "auto",
        team_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        project_id: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        fallback_model: Optional[str] = None,
    ):
        """
        Native tool-calling stream — unified across all providers.

        Yields structured event dicts (not raw text):
          {"type": "text_delta", "delta": str}       — streamed text chunk
          {"type": "reasoning_delta", "delta": str}  — streamed thinking/reasoning chunk
          {"type": "tool_use", "id": str, "name": str, "input": dict}  — complete tool call
          {"type": "message_stop", "stop_reason": str} — end of response with finish reason

        Supports:
          - Anthropic (claude-*)            → true streaming SSE tool calling
          - OpenAI (gpt-*, o*) / OpenRouter → streaming function call chunks
          - Gemini (gemini-*)               → non-streaming generateContent
          - Ollama / Nvidia / others        → fallback to text stream (no tools)
        """
        response_text = ""
        provider = "unknown"
        emitted_event = False

        try:
            if model.startswith("claude"):
                if self.anthropic_key:
                    provider = "anthropic"
                    async for event in self._anthropic_tool_stream(
                        model, system_prompt, messages, tools,
                        temperature, max_tokens, tool_choice, reasoning_effort,
                    ):
                        if event["type"] == "text_delta":
                            response_text += event["delta"]
                        emitted_event = True
                        yield event
                elif self.openrouter_key:
                    # Fallback: route via OpenRouter (OpenAI-compat function calling)
                    provider = "openrouter"
                    target = f"anthropic/{model}" if "/" not in model else model
                    target = target.replace("claude-3-5-sonnet", "claude-3.5-sonnet").replace("-20241022", "")
                    async for event in self._openai_tool_stream(
                        "https://openrouter.ai/api/v1/chat/completions",
                        self.openrouter_key, target,
                        system_prompt, messages, tools,
                        temperature, max_tokens, tool_choice,
                    ):
                        if event["type"] == "text_delta":
                            response_text += event["delta"]
                        emitted_event = True
                        yield event
                else:
                    provider = "anthropic"
                    async for event in self._anthropic_tool_stream(
                        model, system_prompt, messages, tools,
                        temperature, max_tokens, tool_choice, reasoning_effort,
                    ):
                        if event["type"] == "text_delta":
                            response_text += event["delta"]
                        emitted_event = True
                        yield event

            elif model.startswith("gemini"):
                provider = "google"
                async for event in self._gemini_tool_stream(
                    model, system_prompt, messages, tools, temperature, max_tokens,
                ):
                    if event["type"] == "text_delta":
                        response_text += event["delta"]
                    yield event

            elif model.startswith("openrouter/"):
                provider = "openrouter"
                target = (
                    model
                    if model in ("openrouter/free", "openrouter/auto")
                    else model[len("openrouter/"):]
                )
                async for event in self._openai_tool_stream(
                    "https://openrouter.ai/api/v1/chat/completions",
                    self.openrouter_key, target,
                    system_prompt, messages, tools,
                    temperature, max_tokens, tool_choice,
                ):
                    if event["type"] == "text_delta":
                        response_text += event["delta"]
                    yield event

            elif model.startswith("ollama/") or model.startswith("nvidia/"):
                # These providers don't support structured tool calling via this client.
                # Fall back to text stream; the old intent-engine path won't run because
                # we're in the native loop, so agent will just get plain text with no tools.
                provider = "ollama" if model.startswith("ollama/") else "nvidia"
                logger.warning(
                    "[generate_with_tools] Provider '%s' does not support native tool calling. "
                    "Falling back to text-only stream.", provider
                )
                async for chunk in self.generate_stream(
                    model, system_prompt, messages,
                    temperature=temperature, max_tokens=max_tokens,
                ):
                    response_text += chunk
                    emitted_event = True
                    yield {"type": "text_delta", "delta": chunk}
                emitted_event = True
                yield {"type": "message_stop", "stop_reason": "stop"}

            else:
                # GPT-*, o-series, or any other OpenAI-compat model
                if self.openai_key:
                    provider = "openai"
                    async for event in self._openai_tool_stream(
                        "https://api.openai.com/v1/chat/completions",
                        self.openai_key, model,
                        system_prompt, messages, tools,
                        temperature, max_tokens, tool_choice,
                    ):
                        if event["type"] == "text_delta":
                            response_text += event["delta"]
                        emitted_event = True
                        yield event
                elif self.openrouter_key:
                    provider = "openrouter"
                    target = f"openai/{model}" if "/" not in model else model
                    async for event in self._openai_tool_stream(
                        "https://openrouter.ai/api/v1/chat/completions",
                        self.openrouter_key, target,
                        system_prompt, messages, tools,
                        temperature, max_tokens, tool_choice,
                    ):
                        if event["type"] == "text_delta":
                            response_text += event["delta"]
                        emitted_event = True
                        yield event
                else:
                    provider = "openai"
                    async for event in self._openai_tool_stream(
                        "https://api.openai.com/v1/chat/completions",
                        self.openai_key, model,
                        system_prompt, messages, tools,
                        temperature, max_tokens, tool_choice,
                    ):
                        if event["type"] == "text_delta":
                            response_text += event["delta"]
                        emitted_event = True
                        yield event

        except LLMProviderError as e:
            fallback_model = (fallback_model or "").strip()
            if not emitted_event and fallback_model and fallback_model != model:
                logger.warning(
                    "[generate_with_tools] Primary model '%s' failed: %s. Falling back to '%s'.",
                    model, e, fallback_model
                )
                async for event in self.generate_with_tools(
                    model=fallback_model,
                    system_prompt=system_prompt,
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tool_choice=tool_choice,
                    team_id=team_id,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    project_id=project_id,
                    reasoning_effort=reasoning_effort,
                    fallback_model=None,
                ):
                    yield event
                return
            raise
        finally:
            if project_id or team_id or agent_id:
                asyncio.create_task(self._log_usage(
                    provider=provider, model=model,
                    system_prompt=system_prompt, messages=messages,
                    response_text=response_text,
                    project_id=project_id, team_id=team_id,
                    agent_id=agent_id, agent_name=agent_name,
                ))

    async def _anthropic_tool_stream(
        self,
        model: str,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
        tool_choice: str,
        reasoning_effort: Optional[str] = None,
    ):
        """
        Anthropic SSE tool-calling stream.
        """
        if not self.anthropic_key:
            raise LLMProviderError(ERROR_MISSING_KEY, "anthropic", model, env_key_name="ANTHROPIC_API_KEY")

        headers = {
            "x-api-key": self.anthropic_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        formatted_messages = self._format_messages_for_provider(messages, "anthropic")

        # Prompt caching for large system prompts
        if len(system_prompt) > 1024:
            system_payload: Any = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
        else:
            system_payload = system_prompt

        payload: dict = {
            "model": model,
            "system": system_payload,
            "messages": formatted_messages,
            "tools": tools,
            "tool_choice": {"type": tool_choice},
            "max_tokens": max_tokens,
            "stream": True,
        }

        thinking_budget = _anthropic_thinking_budget(reasoning_effort, max_tokens)
        if thinking_budget is not None:
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }
            payload["temperature"] = 1
        else:
            payload["temperature"] = temperature

        for attempt in range(3):
            received_data = False
            stopped = False
            current_tool_id = None
            current_tool_name = None
            current_json_chunks = []
            try:
                async with self._http_client.stream(
                    "POST", "https://api.anthropic.com/v1/messages",
                    headers=headers, json=payload,
                ) as response:
                    if response.status_code != 200:
                        err = await response.aread()
                        error = LLMProviderError.classify_http_error(
                            response.status_code,
                            err.decode("utf-8", errors="replace"),
                            "anthropic",
                            model,
                        )
                        if attempt < 2 and (
                            error.error_type == ERROR_RATE_LIMITED
                            or response.status_code >= 500
                        ):
                            await response.aclose()
                            await asyncio.sleep(2 ** attempt + random.uniform(0, 0.5))
                            continue
                        raise error

                    stop_reason: Optional[str] = None
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        received_data = True
                        error = self._sse_error(data, "anthropic", model)
                        if error is not None:
                            raise error

                        event_type = data.get("type", "")

                        if event_type == "content_block_start":
                            block = data.get("content_block", {})
                            if block.get("type") == "tool_use":
                                current_tool_id = block.get("id")
                                current_tool_name = block.get("name")
                                current_json_chunks = []

                        elif event_type == "content_block_delta":
                            delta = data.get("delta", {})
                            dtype = delta.get("type", "")
                            if dtype == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    yield {"type": "text_delta", "delta": text}
                            elif dtype == "input_json_delta":
                                current_json_chunks.append(delta.get("partial_json", ""))
                            elif dtype == "thinking_delta":
                                thinking = delta.get("thinking", "")
                                if thinking:
                                    yield {"type": "reasoning_delta", "delta": thinking}

                        elif event_type == "content_block_stop":
                            if current_tool_id and current_tool_name:
                                json_str = "".join(current_json_chunks)
                                try:
                                    tool_input = json.loads(json_str) if json_str.strip() else {}
                                except json.JSONDecodeError as exc:
                                    raise LLMProviderError(
                                        ERROR_PROVIDER_DOWN, "anthropic", model,
                                        message="Provider returned invalid tool arguments.",
                                    ) from exc
                                if not isinstance(tool_input, dict):
                                    raise LLMProviderError(
                                        ERROR_PROVIDER_DOWN, "anthropic", model,
                                        message="Tool arguments must be a JSON object.",
                                    )
                                yield {
                                    "type": "tool_use",
                                    "id": current_tool_id,
                                    "name": current_tool_name,
                                    "input": tool_input,
                                }
                                current_tool_id = None
                                current_tool_name = None
                                current_json_chunks = []

                        elif event_type == "message_delta":
                            stop_reason = data.get("delta", {}).get("stop_reason")

                        elif event_type == "message_stop":
                            stopped = True
                            yield {"type": "message_stop", "stop_reason": stop_reason or "end_turn"}
                            break

                if not stopped:
                    raise LLMProviderError(
                        ERROR_PROVIDER_DOWN, "anthropic", model,
                        message="Tool stream ended without message_stop.",
                    )
                return  # Success

            except httpx.TransportError as e:
                if not received_data and attempt < 2:
                    logger.warning("Anthropic tool stream connection error: %s. Retrying...", e)
                    await asyncio.sleep(2 ** attempt + random.uniform(0, 0.5))
                else:
                    raise LLMProviderError(ERROR_PROVIDER_DOWN, "anthropic", model, message=f"Connection Error: {e}")
            except LLMProviderError:
                raise

        raise LLMProviderError(ERROR_PROVIDER_DOWN, "anthropic", model)

    async def _openai_tool_stream(
        self,
        url: str,
        key: Optional[str],
        model: str,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
        tool_choice: str,
    ):
        """
        OpenAI-compatible streaming function calling.
        """
        provider, _ = _provider_from_url(url)
        if "api.openai.com" in url and not key:
            raise LLMProviderError(ERROR_MISSING_KEY, "openai", model, env_key_name="OPENAI_API_KEY")
        if "openrouter.ai" in url and not key:
            raise LLMProviderError(ERROR_MISSING_KEY, "openrouter", model, env_key_name="OPENROUTER_API_KEY")

        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"

        formatted = self._format_messages_for_provider(messages, "openai")
        final_messages = [{"role": "system", "content": system_prompt}] + formatted

        # Map tool_choice string to OpenAI format
        if tool_choice == "auto":
            tc_param: Any = "auto"
        elif tool_choice == "none":
            tc_param = "none"
        elif tool_choice in ("required", "any"):
            tc_param = "required"
        else:
            raise ValueError(f"Unsupported tool_choice: {tool_choice!r}")

        payload: dict = {
            "model": model,
            "messages": final_messages,
            "tools": tools,
            "tool_choice": tc_param,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        for attempt in range(3):
            tool_calls_acc = {}
            accumulated_text = []
            finish_reason = None
            received_data = False
            stopped = False
            try:
                async with self._http_client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        err = await response.aread()
                        error = LLMProviderError.classify_http_error(
                            response.status_code,
                            err.decode("utf-8", errors="replace"),
                            provider,
                            model,
                        )
                        if attempt < 2 and (
                            error.error_type == ERROR_RATE_LIMITED
                            or response.status_code >= 500
                        ):
                            await response.aclose()
                            await asyncio.sleep(2 ** attempt + random.uniform(0, 0.5))
                            continue
                        raise error

                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            stopped = True
                            break
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        received_data = True
                        error = self._sse_error(data, provider, model)
                        if error is not None:
                            raise error

                        choices = data.get("choices", [])
                        if not choices:
                            continue

                        choice = choices[0]
                        delta = choice.get("delta", {})
                        fr = choice.get("finish_reason")
                        if fr:
                            finish_reason = fr

                        # Stream reasoning content if present (o1/o3/reasoning models)
                        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                        if reasoning:
                            yield {"type": "reasoning_delta", "delta": reasoning}

                        # Stream text content
                        text = delta.get("content") or ""
                        if text:
                            accumulated_text.append(text)
                            yield {"type": "text_delta", "delta": text}

                        # Accumulate tool call chunks
                        for tc in delta.get("tool_calls", []):
                            idx = tc.get("index", 0)
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                            if tc.get("id"):
                                tool_calls_acc[idx]["id"] = tc["id"]
                            fn = tc.get("function", {})
                            if fn.get("name"):
                                tool_calls_acc[idx]["name"] = fn["name"]
                            if fn.get("arguments"):
                                tool_calls_acc[idx]["arguments"] += fn["arguments"]

                if not stopped or finish_reason is None:
                    raise LLMProviderError(
                        ERROR_PROVIDER_DOWN, provider, model,
                        message="Tool stream ended without a completion marker.",
                    )

                # Never execute truncated or otherwise unfinished tool calls.
                if tool_calls_acc and finish_reason != "tool_calls":
                    raise LLMProviderError(
                        ERROR_PROVIDER_DOWN, provider, model,
                        message=f"Tool generation did not complete: {finish_reason}.",
                    )

                # Validate every call before exposing any for execution.
                completed_calls = []
                for idx in sorted(tool_calls_acc):
                    tc = tool_calls_acc[idx]
                    arg_str = tc.get("arguments", "")
                    try:
                        tool_input = json.loads(arg_str) if arg_str.strip() else {}
                    except json.JSONDecodeError as exc:
                        raise LLMProviderError(
                            ERROR_PROVIDER_DOWN, provider, model,
                            message="Provider returned invalid tool arguments.",
                        ) from exc
                    if not isinstance(tool_input, dict) or not tc.get("name") or not tc.get("id"):
                        raise LLMProviderError(
                            ERROR_PROVIDER_DOWN, provider, model,
                            message="Provider returned an invalid tool call.",
                        )
                    completed_calls.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tool_input,
                    })

                # Fallback: check if an open-source model leaked tool calls as raw text/XML tags
                if not completed_calls and accumulated_text:
                    full_text = "".join(accumulated_text)
                    if "<dots_function_call>" in full_text or "<invoke" in full_text:
                        import uuid as _uuid
                        # 1. Dots studio format: <dots_function_call> <fn_name> args </fn_name> </dots_function_call>
                        for m in re.finditer(r"<dots_function_call>\s*<([a-zA-Z0-9_-]+)>\s*(.*?)\s*</\1>\s*</dots_function_call>", full_text, re.DOTALL):
                            fn_name = m.group(1).strip()
                            fn_arg = m.group(2).strip()
                            tool_input = {}
                            if fn_arg.startswith("{") and fn_arg.endswith("}"):
                                try:
                                    tool_input = json.loads(fn_arg)
                                except Exception:
                                    tool_input = {"raw": fn_arg}
                            elif fn_arg:
                                if fn_name in ("list_directory", "list_dir"):
                                    tool_input = {"path": fn_arg}
                                elif fn_name in ("read_file", "view_file"):
                                    tool_input = {"path": fn_arg}
                                else:
                                    tool_input = {"input": fn_arg}
                            completed_calls.append({
                                "type": "tool_use",
                                "id": f"call_{_uuid.uuid4().hex[:12]}",
                                "name": fn_name,
                                "input": tool_input,
                            })
                        # 2. Invoke XML format: <invoke name="..."><parameter name="...">...</parameter></invoke>
                        for m in re.finditer(r'<invoke\s+name=["\']([a-zA-Z0-9_-]+)["\']\s*>(.*?)</invoke>', full_text, re.DOTALL):
                            fn_name = m.group(1).strip()
                            fn_body = m.group(2).strip()
                            params = {}
                            for pm in re.finditer(r'<parameter\s+name=["\']([a-zA-Z0-9_-]+)["\']\s*>(.*?)</parameter>', fn_body, re.DOTALL):
                                params[pm.group(1).strip()] = pm.group(2).strip()
                            if not params and fn_body.startswith("{") and fn_body.endswith("}"):
                                try:
                                    params = json.loads(fn_body)
                                except Exception:
                                    pass
                            completed_calls.append({
                                "type": "tool_use",
                                "id": f"call_{_uuid.uuid4().hex[:12]}",
                                "name": fn_name,
                                "input": params or {"input": fn_body},
                            })

                for event in completed_calls:
                    yield event

                yield {"type": "message_stop", "stop_reason": finish_reason or "stop"}
                return  # Success

            except httpx.TransportError as e:
                if not received_data and attempt < 2:
                    logger.warning("OpenAI tool stream connection error: %s. Retrying...", e)
                    await asyncio.sleep(2 ** attempt + random.uniform(0, 0.5))
                else:
                    raise LLMProviderError(
                        ERROR_PROVIDER_DOWN, provider, model,
                        message=f"Provider connection failed ({type(e).__name__}).",
                    ) from e
            except LLMProviderError:
                raise
            except Exception as e:
                raise LLMProviderError(
                    ERROR_PROVIDER_DOWN, provider, model,
                    message="Invalid tool-stream response.",
                ) from e

        raise LLMProviderError(ERROR_PROVIDER_DOWN, provider, model)

    async def _gemini_tool_stream(
        self,
        model: str,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ):
        """
        Gemini native function calling via generateContent (non-streaming).

        Gemini's function calling response arrives in a single JSON response with
        a ``functionCall`` part when the model wants to call a tool, or a ``text``
        part when it's responding with natural language.
        """
        if not self.gemini_key:
            raise LLMProviderError(ERROR_MISSING_KEY, "google", model, env_key_name="GOOGLE_API_KEY")

        contents = self._format_messages_for_provider(messages, "google")

        payload: dict = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "tools": tools,  # [{"functionDeclarations": [...]}]
            "tool_config": {"function_calling_config": {"mode": "AUTO"}},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
            f":generateContent?key={self.gemini_key}"
        )

        try:
            response = await self._http_client.post(url, json=payload)
            if response.status_code != 200:
                raise LLMProviderError.classify_http_error(
                    response.status_code, response.text, "google", model
                )

            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                yield {"type": "message_stop", "stop_reason": "stop"}
                return

            finish_reason = candidates[0].get("finishReason", "STOP")
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "text" in part and part["text"]:
                    yield {"type": "text_delta", "delta": part["text"]}
                elif "functionCall" in part:
                    fc = part["functionCall"]
                    # Gemini sends args as a dict already (not a JSON string)
                    args = fc.get("args", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {"_raw": args}
                    # Generate a unique ID for this function call
                    import uuid as _uuid
                    yield {
                        "type": "tool_use",
                        "id": f"gemini_{_uuid.uuid4().hex[:12]}",
                        "name": fc.get("name", ""),
                        "input": args,
                    }

            yield {"type": "message_stop", "stop_reason": finish_reason}

        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(ERROR_PROVIDER_DOWN, "google", model, message=f"Gemini Tool Call Exception: {e}")

    async def generate_stream_with_reasoning(
        self,
        model: str,
        system_prompt: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        project_id: str | None = None,
        team_id: str | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
        fallback_model: str | None = None,
        reasoning_effort: str = "none",
    ):
        """
        Like generate_stream_with_fallback, but yields dicts:
          {"content": str, "reasoning": str}
        Reasoning will be non-empty for models that support it
        (DeepSeek R1 via OpenRouter, Claude extended thinking, OpenAI o-series).
        """
        emitted = False
        primary = self._generate_stream_rich(
            model, system_prompt, messages, temperature, max_tokens,
            project_id, team_id, agent_id, agent_name, reasoning_effort
        )
        try:
            async with aclosing(primary):
                async for chunk in primary:
                    if chunk.get("content") or chunk.get("reasoning"):
                        emitted = True
                    yield chunk
            return
        except LLMProviderError:
            fallback = (fallback_model or "").strip()
            if emitted or not fallback or fallback == model:
                raise
            logger.warning("Primary model %s failed; falling back to %s", model, fallback)

        secondary = self._generate_stream_rich(
            fallback, system_prompt, messages, temperature, max_tokens,
            project_id, team_id, agent_id, agent_name, reasoning_effort
        )
        async with aclosing(secondary):
            async for chunk in secondary:
                yield chunk

    async def _generate_stream_rich(
        self,
        model: str,
        system_prompt: str,
        messages: list,
        temperature: float,
        max_tokens: int,
        project_id: str | None,
        team_id: str | None,
        agent_id: str | None,
        agent_name: str | None,
        reasoning_effort: str,
    ):
        """
        Core rich-stream implementation yielding {content, reasoning} dicts.
        Re-uses existing per-provider SSE parsing with the updated extractor.
        """
        system_prompt, messages, max_tokens = clamp_context_for_model(
            model, system_prompt, messages, max_tokens
        )
        _effort = reasoning_effort if reasoning_effort and reasoning_effort != "none" else None
        response_text = ""
        provider = "unknown"

        async def _wrap_openai_compatible(url, key, mdl, extra=None):
            nonlocal response_text, provider
            headers = {"Content-Type": "application/json"}
            if key:
                headers["Authorization"] = f"Bearer {key}"
            formatted_msgs = self._format_messages_for_provider(messages, "openai")
            formatted = [{"role": "system", "content": system_prompt}] + formatted_msgs
            payload: dict = {
                "model": mdl, "messages": formatted,
                "temperature": temperature, "max_tokens": max_tokens, "stream": True
            }
            if extra:
                payload.update(extra)
            async for chunk in self._stream_with_retry_rich(url, headers, payload, "openai"):
                response_text += chunk["content"]
                yield chunk

        async def _wrap_anthropic(mdl):
            nonlocal response_text, provider
            _BUDGETS = {"low": 1024, "medium": 4096, "high": 8192}
            headers = {
                "x-api-key": self.anthropic_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            formatted_msgs = self._format_messages_for_provider(messages, "anthropic")
            payload: dict = {
                "model": mdl, "system": system_prompt, "messages": formatted_msgs,
                "max_tokens": max_tokens, "stream": True
            }
            thinking_budget = _anthropic_thinking_budget(_effort, max_tokens)
            if thinking_budget is not None:
                payload["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": thinking_budget,
                }
                payload["temperature"] = 1
            else:
                payload["temperature"] = temperature
            async for chunk in self._stream_with_retry_rich("https://api.anthropic.com/v1/messages", headers, payload, "anthropic"):
                response_text += chunk["content"]
                yield chunk

        try:
            if model.startswith("openrouter/"):
                provider = "openrouter"
                use_special = model in ("openrouter/free", "openrouter/auto")
                target = model if use_special else model[len("openrouter/"):]
                extra = {"reasoning": {"enabled": True}} if use_special else ({"reasoning": {"effort": _effort}} if _effort else None)
                async for c in _wrap_openai_compatible("https://openrouter.ai/api/v1/chat/completions", self.openrouter_key, target, extra): yield c

            elif model.startswith("nvidia/"):
                provider = "nvidia"
                async for c in _wrap_openai_compatible("https://integrate.api.nvidia.com/v1/chat/completions", self.nvidia_key, model.replace("nvidia/", "", 1)): yield c

            elif model.startswith("ollama/"):
                provider = "ollama"
                async for c in _wrap_openai_compatible(f"{self.ollama_base_url}/chat/completions", None, model.replace("ollama/", "", 1)): yield c

            elif model.startswith("gemini"):
                provider = "google"
                # Gemini doesn't expose a reasoning stream — treat all output as content
                async for chunk in self._stream_gemini(model, system_prompt, messages, temperature, max_tokens):
                    response_text += chunk
                    yield {"content": chunk, "reasoning": ""}

            elif model.startswith("claude"):
                if self.anthropic_key:
                    provider = "anthropic"
                    async for c in _wrap_anthropic(model): yield c
                elif self.openrouter_key:
                    provider = "openrouter"
                    target = f"anthropic/{model}" if "/" not in model else model
                    target = target.replace("claude-3-5-sonnet", "claude-3.5-sonnet").replace("-20241022", "")
                    extra = {"reasoning": {"effort": _effort}} if _effort else None
                    async for c in _wrap_openai_compatible("https://openrouter.ai/api/v1/chat/completions", self.openrouter_key, target, extra): yield c
                else:
                    provider = "anthropic"
                    async for c in _wrap_anthropic(model): yield c

            else:
                _is_o = any(model.startswith(p) for p in ("o1", "o3", "o4"))
                extra = {"reasoning_effort": _effort} if _effort and _is_o else None
                if self.openai_key:
                    provider = "openai"
                    async for c in _wrap_openai_compatible("https://api.openai.com/v1/chat/completions", self.openai_key, model, extra): yield c
                elif self.openrouter_key:
                    provider = "openrouter"
                    target = f"openai/{model}" if "/" not in model else model
                    extra2 = {"reasoning": {"effort": _effort}} if _effort else None
                    async for c in _wrap_openai_compatible("https://openrouter.ai/api/v1/chat/completions", self.openrouter_key, target, extra2): yield c
                else:
                    provider = "openai"
                    async for c in _wrap_openai_compatible("https://api.openai.com/v1/chat/completions", self.openai_key, model, extra): yield c
        finally:
            if project_id or team_id or agent_id:
                asyncio.create_task(self._log_usage(
                    provider=provider, model=model,
                    system_prompt=system_prompt, messages=messages,
                    response_text=response_text,
                    project_id=project_id, team_id=team_id,
                    agent_id=agent_id, agent_name=agent_name
                ))

    # ================================================================
    # Embeddings (with Gemini fallback)
    # ================================================================

    async def generate_embeddings(self, text: str) -> List[float]:
        """
        Generates a vector embedding for the input text.
        Honors DEFAULT_EMBEDDING_MODEL if configured, otherwise follows waterfall cascade:
        OpenAI -> Gemini -> OpenRouter -> Ollama.
        """
        import core.config
        configured = getattr(core.config, "DEFAULT_EMBEDDING_MODEL", "auto")

        # 1. Direct provider routing if user explicitly specified a model
        if configured and configured != "auto":
            conf_lower = configured.lower()
            if "gemini" in conf_lower and self.gemini_key:
                res = await self._embeddings_gemini(text)
                if res: return res
            elif ("openai" in conf_lower or "text-embedding" in conf_lower) and self.openai_key:
                model_name = "text-embedding-3-large" if "large" in conf_lower else "text-embedding-3-small"
                res = await self._embeddings_openai(text, model=model_name)
                if res: return res
            elif "nemotron" in conf_lower and self.openrouter_key:
                res = await self._embeddings_openrouter(text)
                if res: return res
            elif "ollama" in conf_lower:
                model_name = conf_lower.replace("ollama/", "") if "/" in conf_lower else conf_lower
                res = await self._embeddings_ollama(text, model=model_name)
                if res: return res

        # 2. Fallback waterfall cascade
        if self.openai_key:
            result = await self._embeddings_openai(text)
            if result:
                return result

        if self.gemini_key:
            result = await self._embeddings_gemini(text)
            if result:
                return result

        if self.openrouter_key:
            result = await self._embeddings_openrouter(text)
            if result:
                return result

        # Try local Ollama if running
        result = await self._embeddings_ollama(text)
        if result:
            return result

        # No keys available or all providers failed — raise explicit error
        raise RuntimeError(
            "No embedding provider configured or available. Please configure an OpenAI, Gemini, or OpenRouter API key, or start Ollama."
        )

    async def _embeddings_openai(self, text: str, model: str = "text-embedding-3-small") -> Optional[List[float]]:
        """OpenAI embeddings (1536 dimensions for small, truncated to 1536 for large)."""
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": text,
            "model": model,
            "dimensions": 1536
        }

        try:
            response = await self._http_client.post(
                "https://api.openai.com/v1/embeddings",
                headers=headers,
                json=payload
            )
            if response.status_code == 200:
                data = response.json()
                return data["data"][0]["embedding"]
            else:
                logger.warning("OpenAI Embeddings error: %s", response.text[:200])
                return None
        except Exception as e:
            logger.warning("OpenAI Embeddings connection error: %s", e)
            return None

    async def _embeddings_gemini(self, text: str) -> Optional[List[float]]:
        """Google Gemini text-embedding-004 (768 dimensions, zero-padded to 1536)."""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004"
            f":embedContent?key={self.gemini_key}"
        )
        payload = {
            "model": "models/text-embedding-004",
            "content": {
                "parts": [{"text": text[:2048]}]  # Gemini embedding input limit
            }
        }

        try:
            response = await self._http_client.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                values = data.get("embedding", {}).get("values", [])
                if values:
                    # Zero-pad from 768 to 1536 to match pgvector column dimension
                    while len(values) < 1536:
                        values.append(0.0)
                    return values[:1536]
                return None
            else:
                logger.warning("Gemini Embeddings error: %s", response.text[:200])
                return None
        except Exception as e:
            logger.warning("Gemini Embeddings connection error: %s", e)
            return None

    async def _embeddings_openrouter(self, text: str) -> Optional[List[float]]:
        """OpenRouter NVIDIA Nemotron 3 Embed 1B (padded/truncated to 1536)."""
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": text,
            "model": "nvidia/nemotron-3-embed-1b:free"
        }

        try:
            response = await self._http_client.post(
                "https://openrouter.ai/api/v1/embeddings",
                headers=headers,
                json=payload
            )
            if response.status_code == 200:
                data = response.json()
                values = data["data"][0]["embedding"]
                if values:
                    # Pad or truncate to 1536
                    while len(values) < 1536:
                        values.append(0.0)
                    return values[:1536]
                return None
            else:
                logger.warning("OpenRouter Embeddings error: %s", response.text[:200])
                return None
        except Exception as e:
            logger.warning("OpenRouter Embeddings connection error: %s", e)
            return None

    async def _embeddings_ollama(self, text: str, model: str = "nomic-embed-text") -> Optional[List[float]]:
        """Local Ollama embeddings (e.g. nomic-embed-text or all-minilm, zero-padded/truncated to 1536)."""
        ollama_host = (self.ollama_base_url or "http://localhost:11434/v1").removesuffix("/v1").rstrip("/")
        payload = {
            "model": model,
            "prompt": text
        }
        try:
            response = await self._http_client.post(
                f"{ollama_host}/api/embeddings",
                json=payload,
                timeout=5.0
            )
            if response.status_code == 200:
                data = response.json()
                values = data.get("embedding", [])
                if values:
                    while len(values) < 1536:
                        values.append(0.0)
                    return values[:1536]
            return None
        except Exception:
            return None


    # Alias for compatibility with older code paths
    get_embedding = generate_embeddings

    def _format_messages_for_provider(
        self,
        messages: List[Dict[str, Any]],
        provider: str
    ) -> List[Dict[str, Any]]:
        """
        Transforms our internal canonical message dicts into provider-specific payloads.
        Supports multimodal content blocks (text, image, document).
        """
        import base64
        import os
        import logging as _logging
        _log = _logging.getLogger("carole.router.formatter")

        formatted = []
        for msg in messages:
            # Already formatted Gemini messages must retain functionCall,
            # functionResponse, and thoughtSignature fields.
            if provider == "google" and "parts" in msg:
                formatted.append(dict(msg))
                continue

            content = msg.get("content")
            if content is None:
                if provider == "openai" and msg.get("tool_calls"):
                    formatted.append(dict(msg))
                    continue
                raise ValueError(
                    f"Message with role {msg.get('role')!r} has no content"
                )

            if isinstance(content, str):
                if provider == "google":
                    roles = {"user": "user", "assistant": "model", "model": "model"}
                    if msg["role"] not in roles:
                        raise ValueError(
                            "Gemini tool results require functionResponse parts"
                        )
                    role = roles[msg["role"]]
                    formatted.append({"role": role, "parts": [{"text": content}]})
                else:
                    formatted.append(dict(msg))
                continue

            if not isinstance(content, list):
                raise ValueError("Message content must be a string or a list")

            # Content is a list (multimodal / structured blocks)
            if provider == "google":
                role = "user" if msg["role"] == "user" else "model"
                parts = []
                for item in content:
                    if item.get("type") == "text":
                        parts.append({"text": item["text"]})
                    elif item.get("type") == "image":
                        local_path = item.get("local_path")
                        if local_path and os.path.exists(local_path):
                            with open(local_path, "rb") as f:
                                b64 = base64.b64encode(f.read()).decode("utf-8")
                            parts.append({
                                "inlineData": {
                                    "mimeType": item.get("mime_type", "image/jpeg"),
                                    "data": b64
                                }
                            })
                        else:
                            _log.warning("Image local_path not found or missing, skipping: %s", local_path)
                    elif item.get("type") == "document":
                        local_path = item.get("local_path")
                        mime = item.get("mime_type", "application/pdf")
                        if local_path and os.path.exists(local_path):
                            if mime == "application/pdf":
                                with open(local_path, "rb") as f:
                                    b64 = base64.b64encode(f.read()).decode("utf-8")
                                parts.append({
                                    "inlineData": {
                                        "mimeType": mime,
                                        "data": b64
                                    }
                                })
                            else:
                                try:
                                    from markitdown import MarkItDown
                                    md = MarkItDown()
                                    result = md.convert(local_path)
                                    parts.append({"text": f"\n[Extracted Document ({mime})]\n{result.text_content}\n[/Extracted Document]\n"})
                                except Exception as e:
                                    parts.append({"text": f"[Error extracting {mime}: {e}]"})
                        else:
                            _log.warning("Document local_path not found, skipping: %s", local_path)
                if parts:
                    formatted.append({"role": role, "parts": parts})

            elif provider == "anthropic":
                parts = []
                for item in content:
                    if item.get("type") in (
                        "tool_use", "tool_result", "thinking", "redacted_thinking"
                    ):
                        parts.append(dict(item))
                    elif item.get("type") in ("image", "document") and "source" in item:
                        parts.append(dict(item))
                    elif item.get("type") == "text":
                        parts.append({"type": "text", "text": item["text"]})
                    elif item.get("type") == "image":
                        local_path = item.get("local_path")
                        if local_path and os.path.exists(local_path):
                            with open(local_path, "rb") as f:
                                b64 = base64.b64encode(f.read()).decode("utf-8")
                            parts.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": item.get("mime_type", "image/jpeg"),
                                    "data": b64
                                }
                            })
                        else:
                            _log.warning("Image local_path not found or missing, skipping: %s", local_path)
                    elif item.get("type") == "document":
                        local_path = item.get("local_path")
                        mime = item.get("mime_type", "application/pdf")
                        if local_path and os.path.exists(local_path):
                            if mime == "application/pdf":
                                with open(local_path, "rb") as f:
                                    b64 = base64.b64encode(f.read()).decode("utf-8")
                                parts.append({
                                    "type": "document",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime,
                                        "data": b64
                                    }
                                })
                            else:
                                try:
                                    from markitdown import MarkItDown
                                    md = MarkItDown()
                                    result = md.convert(local_path)
                                    parts.append({"type": "text", "text": f"\n[Extracted Document ({mime})]\n{result.text_content}\n[/Extracted Document]\n"})
                                except Exception as e:
                                    parts.append({"type": "text", "text": f"[Error extracting {mime}: {e}]"})
                        else:
                            _log.warning("Document local_path not found, skipping: %s", local_path)
                if parts:
                    formatted.append({"role": msg["role"], "content": parts})

            else:
                # OpenAI / OpenRouter format
                parts = []
                for item in content:
                    if item.get("type") in ("image_url", "input_audio", "file"):
                        parts.append(dict(item))
                    elif item.get("type") == "text":
                        parts.append({"type": "text", "text": item["text"]})
                    elif item.get("type") == "image":
                        local_path = item.get("local_path")
                        if local_path and os.path.exists(local_path):
                            with open(local_path, "rb") as f:
                                b64 = base64.b64encode(f.read()).decode("utf-8")
                            mime = item.get("mime_type", "image/jpeg")
                            parts.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime};base64,{b64}"
                                }
                            })
                        else:
                            _log.warning("Image local_path not found or missing, skipping: %s", local_path)
                    elif item.get("type") == "document":
                        local_path = item.get("local_path")
                        mime = item.get("mime_type", "application/pdf")
                        if local_path and os.path.exists(local_path):
                            try:
                                from markitdown import MarkItDown
                                md = MarkItDown()
                                result = md.convert(local_path)
                                parts.append({"type": "text", "text": f"\n[Extracted Document ({mime})]\n{result.text_content}\n[/Extracted Document]\n"})
                            except Exception as e:
                                parts.append({"type": "text", "text": f"[Error extracting {mime}: {e}]"})
                        else:
                            _log.warning("Document local_path not found, skipping: %s", local_path)
                if parts:
                    formatted.append({**msg, "content": parts})

        return formatted


# Global singleton router
llm_router = MultiModelRouter()

