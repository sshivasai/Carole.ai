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



# MODEL_CATALOG and get_active_catalog are now loaded from JSON files.
# Edit:  backend/core/defaults/supported_models.json  (repo defaults)
# Or:    ~/.carole/supported_models.json         (user overrides)
# Or:    Settings UI → Model Catalog tab
from core.llm.model_catalog import load_model_catalog, get_active_catalog  # noqa: F401


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
            yield "[Router Error: OPENAI_API_KEY is not configured.]"
            return
        if "openrouter.ai" in url and not key:
            yield "[Router Error: OPENROUTER_API_KEY is not configured.]"
            return
        if "integrate.api.nvidia.com" in url and not key:
            yield "[Router Error: NVIDIA_API_KEY is not configured.]"
            return

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
            yield "[Router Error: ANTHROPIC_API_KEY is not configured in the backend environment.]"
            return

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
            yield "[Router Error: GOOGLE_API_KEY is not configured in the backend environment.]"
            return

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
                    yield f"[Gemini API Error {response.status_code}: {err_body.decode('utf-8')[:500]}]"
                    return

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
        except Exception as e:
            yield f"[Router Connection Exception (Gemini): {str(e)}]"

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
                        yield f"[API Error {response.status_code}: {err_body.decode('utf-8')[:500]}]"
                        return

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
                    yield f"[Router Connection Error after {max_retries} retries: {str(e)}]"
            except Exception as e:
                yield f"[Router Exception: {str(e)}]"
                return


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
                        yield {"content": f"[API Error {response.status_code}: {err.decode()[:300]}]", "reasoning": ""}
                        return
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
                    yield {"content": f"[Connection Error: {e}]", "reasoning": ""}
            except Exception as e:
                yield {"content": f"[Stream Exception: {e}]", "reasoning": ""}
                return

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

        # No keys available — return mock zero-vector
        return [0.0] * 1536

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
                if parts:
                    formatted.append({"role": msg["role"], "content": parts})
                
        return formatted


# Global singleton router
llm_router = MultiModelRouter()

