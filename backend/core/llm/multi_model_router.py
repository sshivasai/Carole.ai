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
import json
import asyncio
import logging
import httpx
from typing import AsyncGenerator, List, Dict, Optional, Any
from core.llm.config_manager import load_config, get_key

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
    if "gpt-4" in m or "o4" in m or "o3" in m or "llama-3" in m or "deepseek" in m:
        return 128_000
    if "gpt-3.5" in m or "phi" in m or "16k" in m:
        return 16_384
    if "32k" in m or "mistral" in m or "qwen" in m:
        return 32_768
    if "8k" in m:
        return 8_192
    if "4k" in m:
        return 4_096
    if "free" in m or "auto" in m:
        return 32_768
    return 32_768


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

    # 2. If system_prompt alone is still too large for this model's budget
    trimmed_system_prompt = system_prompt
    if current_input_tokens > target_input_token_limit:
        msg_chars = _msg_chars(trimmed_messages)
        max_sys_chars = max(2000, (target_input_token_limit * 4) - msg_chars)
        if len(trimmed_system_prompt) > max_sys_chars:
            trimmed_system_prompt = trimmed_system_prompt[:max_sys_chars] + "\n\n[System prompt truncated to fit model context limit]"
            current_input_chars = len(trimmed_system_prompt) + msg_chars
            current_input_tokens = current_input_chars // 4

    # 3. Calculate safe max_tokens
    available_tokens = ctx_limit - current_input_tokens - 50
    safe_max_tokens = max(128, min(requested_max_tokens, available_tokens))

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
        self.nvidia_key    = get_key(cfg, "nvidia",    "NVIDIA_API_KEY")
        self.ollama_base_url = (
            cfg.get("providers", {}).get("ollama_base_url", "").strip()
            or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        )

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

        error_chunk: Optional[str] = None
        primary_yielded_content = False

        async for chunk in self.generate_stream(
            model, system_prompt, messages, temperature, max_tokens,
            project_id, team_id, agent_id, agent_name,
            reasoning_effort=reasoning_effort,
        ):
            is_error = chunk.startswith("[Router Error") or chunk.startswith("[API Error") or chunk.startswith("[Gemini API Error")
            if is_error and not primary_yielded_content:
                error_chunk = chunk
                break
            primary_yielded_content = True
            yield chunk

        if error_chunk is not None:
            if fallback_model and fallback_model.strip() and fallback_model != model:
                yield f"\n\n⚠️ Primary model `{model}` failed ({error_chunk[:80]}…). Falling back to `{fallback_model}`…\n\n"
                async for chunk in self.generate_stream(
                    fallback_model, system_prompt, messages, temperature, max_tokens,
                    project_id, team_id, agent_id, agent_name,
                    reasoning_effort=reasoning_effort,
                ):
                    yield chunk
            else:
                yield error_chunk


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

            cost = (prompt_tokens * rate_in + completion_tokens * rate_out) / 1_000_000

            from core.memory.database import async_session
            from core.memory.models import TokenUsage, Project
            from sqlalchemy import select
            import uuid

            async with async_session() as session:
                usage = TokenUsage(
                    project_id=uuid.UUID(project_id) if isinstance(project_id, str) else project_id,
                    team_id=uuid.UUID(team_id) if isinstance(team_id, str) else team_id,
                    agent_id=uuid.UUID(agent_id) if isinstance(agent_id, str) else agent_id,
                    agent_name=agent_name,
                    model=model,
                    provider=provider,
                    prompt_tokens=str(prompt_tokens),
                    completion_tokens=str(completion_tokens),
                    total_tokens=str(total_tokens),
                    estimated_cost_usd=f"{cost:.6f}"
                )
                session.add(usage)
                
                # Update Project total spend
                if project_id:
                    proj_uuid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
                    stmt = select(Project).where(Project.id == proj_uuid)
                    result = await session.execute(stmt)
                    project = result.scalars().first()
                    if project:
                        current_spend = float(project.total_spend_usd) if project.total_spend_usd else 0.0
                        project.total_spend_usd = f"{current_spend + cost:.6f}"
                
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
                        "estimated_cost_usd": f"{cost:.6f}",
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

        payload: dict = {
            "model": model,
            "system": system_prompt,
            "messages": formatted_messages,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if reasoning_effort and reasoning_effort in _ANTHROPIC_BUDGETS:
            # Extended thinking — temperature must be 1 (API requirement)
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": _ANTHROPIC_BUDGETS[reasoning_effort],
            }
            payload["temperature"] = 1  # Anthropic requires temp=1 when thinking is on
            # Ensure budget < max_tokens (API requirement)
            if _ANTHROPIC_BUDGETS[reasoning_effort] >= max_tokens:
                payload["max_tokens"] = _ANTHROPIC_BUDGETS[reasoning_effort] + 2048
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

    async def _stream_with_retry(
        self, url: str, headers: dict, payload: dict, parse_format: str,
        max_retries: int = 3
    ) -> AsyncGenerator[str, None]:
        """
        Shared SSE stream parser with retry/backoff.
        parse_format: 'anthropic' or 'openai'
        """
        for attempt in range(max_retries):
            try:
                async with self._http_client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code == 429:
                        # Rate limited — backoff and retry
                        wait = (2 ** attempt) * 2
                        logger.warning(
                            "Rate limited (429). Retrying in %ds... (attempt %d/%d)", wait, attempt + 1, max_retries
                        )
                        await asyncio.sleep(wait)
                        continue

                    if response.status_code >= 500:
                        wait = (2 ** attempt) * 1
                        logger.warning(
                            "Server error (%d). Retrying in %ds...", response.status_code, wait
                        )
                        await asyncio.sleep(wait)
                        continue

                    if response.status_code != 200:
                        err_body = await response.aread()
                        raise LLMProviderError.classify_http_error(response.status_code, err_body.decode('utf-8'), parse_format)

                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            content, _ = self._extract_text_from_sse(data, parse_format)
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
                    return  # Success — don't retry

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                wait = (2 ** attempt) * 1
                if attempt < max_retries - 1:
                    logger.warning(
                        "Connection error: %s. Retrying in %ds... (attempt %d/%d)", e, wait, attempt + 1, max_retries
                    )
                    await asyncio.sleep(wait)
                else:
                    raise LLMProviderError(ERROR_PROVIDER_DOWN, parse_format, message=f"Connection Error after {max_retries} retries: {str(e)}")
            except LLMProviderError:
                raise
            except Exception as e:
                raise LLMProviderError(ERROR_PROVIDER_DOWN, parse_format, message=f"Router Exception: {str(e)}")


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
    # Embeddings (with Gemini fallback)
    # ================================================================

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
        async for chunk in self._generate_stream_rich(
            model, system_prompt, messages, temperature, max_tokens,
            project_id, team_id, agent_id, agent_name, reasoning_effort
        ):
            yield chunk

        # Fallback on first-chunk error
        # (handled inside _generate_stream_rich — this outer wrapper is for future use)

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
            if _effort and _effort in _BUDGETS:
                payload["thinking"] = {"type": "enabled", "budget_tokens": _BUDGETS[_effort]}
                payload["temperature"] = 1
                if _BUDGETS[_effort] >= max_tokens:
                    payload["max_tokens"] = _BUDGETS[_effort] + 2048
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

    async def _stream_with_retry_rich(
        self, url: str, headers: dict, payload: dict, parse_format: str,
        max_retries: int = 3
    ):
        """
        Like _stream_with_retry but yields {content, reasoning} dicts.
        Uses the shared persistent HTTP client for connection reuse.
        """
        for attempt in range(max_retries):
            try:
                async with self._http_client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code == 429:
                        wait = (2 ** attempt) * 2
                        logger.warning("Rate limited (429) in rich stream. Retrying in %ds...", wait)
                        await asyncio.sleep(wait)
                        continue
                    if response.status_code >= 500:
                        wait = 2 ** attempt
                        logger.warning("Server error (%d) in rich stream. Retrying in %ds...", response.status_code, wait)
                        await asyncio.sleep(wait)
                        continue
                    if response.status_code != 200:
                        err = await response.aread()
                        raise LLMProviderError.classify_http_error(response.status_code, err.decode(), parse_format)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            content, reasoning = self._extract_text_from_sse(data, parse_format)
                            if content or reasoning:
                                yield {"content": content, "reasoning": reasoning}
                        except json.JSONDecodeError:
                            continue
                    return
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                if attempt < max_retries - 1:
                    logger.warning("Connection error in rich stream: %s. Retrying...", e)
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise LLMProviderError(ERROR_PROVIDER_DOWN, parse_format, message=f"Connection Error: {e}")
            except LLMProviderError:
                raise
            except Exception as e:
                raise LLMProviderError(ERROR_PROVIDER_DOWN, parse_format, message=f"Stream Exception: {e}")

    # ================================================================
    # Embeddings (with Gemini fallback)
    # ================================================================

    async def generate_embeddings(self, text: str) -> List[float]:
        """
        Generates a vector embedding for the input text.
        Tries OpenAI first (1536-dim), falls back to Gemini (768-dim, zero-padded to 1536).
        Returns a zero vector if no API key is available.
        """
        # Try OpenAI first
        if self.openai_key:
            result = await self._embeddings_openai(text)
            if result:
                return result

        # Fallback to Gemini
        if self.gemini_key:
            result = await self._embeddings_gemini(text)
            if result:
                return result

        # Fallback to OpenRouter (NVIDIA Nemotron 3 Embed 1B free)
        if self.openrouter_key:
            result = await self._embeddings_openrouter(text)
            if result:
                return result

        # No keys available or all providers failed — raise explicit error
        raise RuntimeError(
            "No embedding provider configured or available. Please configure an OpenAI, Gemini, or OpenRouter API key."
        )

    async def _embeddings_openai(self, text: str) -> Optional[List[float]]:
        """OpenAI text-embedding-3-small (1536 dimensions)."""
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": text,
            "model": "text-embedding-3-small"
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


    # Alias for compatibility with older code paths
    get_embedding = generate_embeddings

    def _format_messages_for_provider(self, messages: List[Dict[str, Any]], provider: str) -> List[Dict[str, Any]]:
        """Converts the internal message format (with local_path images) into provider-specific payloads.
        
        File I/O is done synchronously here because this runs in an async context only during
        stream setup — not inside a hot loop. For very large images, consider offloading via
        asyncio.to_thread if needed in the future.
        """
        import base64
        import os
        import logging as _logging
        _log = _logging.getLogger("carole.router.formatter")
        
        formatted = []
        for msg in messages:
            content = msg["content"]
            if isinstance(content, str):
                if provider == "google":
                    role = "user" if msg["role"] == "user" else "model"
                    formatted.append({"role": role, "parts": [{"text": content}]})
                else:
                    formatted.append({"role": msg["role"], "content": content})
                continue
                
            # Content is a list (multimodal)
            if provider == "google":
                role = "user" if msg["role"] == "user" else "model"
                parts = []
                for item in content:
                    if item["type"] == "text":
                        parts.append({"text": item["text"]})
                    elif item["type"] == "image":
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
                    elif item["type"] == "document":
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
                    if item["type"] == "text":
                        parts.append({"type": "text", "text": item["text"]})
                    elif item["type"] == "image":
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
                    elif item["type"] == "document":
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
                    if item["type"] == "text":
                        parts.append({"type": "text", "text": item["text"]})
                    elif item["type"] == "image":
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
                    elif item["type"] == "document":
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
                    formatted.append({"role": msg["role"], "content": parts})
                
        return formatted


# Global singleton router
llm_router = MultiModelRouter()

