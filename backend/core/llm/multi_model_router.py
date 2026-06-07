"""
# backend/core/llm/multi_model_router.py

This module acts as the gateway to route LLM requests to different providers.

Supported Providers:
1. Anthropic (Claude models e.g. claude-3-5-sonnet, claude-sonnet-4, claude-opus-4)
2. OpenAI (GPT models e.g. gpt-4o, gpt-4o-mini)
3. Google Gemini (e.g. gemini-2.0-flash, gemini-2.5-pro)
4. Qwen (Via DashScope, OpenRouter, or local vLLM/Ollama OpenAI-compatible endpoint)

Features:
- Standard generation completions.
- Asynchronous generator streaming (crucial for live-streaming agent thoughts to the WebSocket EventBus).
- Dynamic fallback or base-URL configuration for local LLMs.
- Gemini embeddings fallback when OpenAI key is unavailable.
- Retry with exponential backoff for transient API failures.
"""

import os
import json
import asyncio
import httpx
from typing import AsyncGenerator, List, Dict, Optional


class MultiModelRouter:
    def __init__(self):
        # Load API keys and configurations
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.gemini_key = os.getenv("GOOGLE_API_KEY")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.nvidia_key = os.getenv("NVIDIA_API_KEY")

        # Configurations
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

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
        agent_name: Optional[str] = None
    ) -> str:
        """
        Generates a standard non-streaming text completion.
        """
        response_text = ""
        async for chunk in self.generate_stream(
            model, system_prompt, messages, temperature, max_tokens,
            project_id, team_id, agent_id, agent_name
        ):
            response_text += chunk
        return response_text

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
        agent_name: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronous generator streaming chunks of the completion in real-time.
        Routes to the correct provider based on model name prefix.
        Tracks token usage upon completion.
        """
        response_text = ""
        provider = "unknown"
        try:
            if model.startswith("openrouter/"):
                provider = "openrouter"
                async for chunk in self._stream_openai_compatible(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    key=self.openrouter_key,
                    model=model,
                    system_prompt=system_prompt,
                    messages=messages,
                    temp=temperature,
                    max_tokens=max_tokens
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
                    max_tokens=max_tokens
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
                    max_tokens=max_tokens
                ):
                    response_text += chunk
                    yield chunk

            elif model.startswith("gemini"):
                provider = "google"
                async for chunk in self._stream_gemini(model, system_prompt, messages, temperature, max_tokens):
                    response_text += chunk
                    yield chunk

            elif model.startswith("claude"):
                if self.openrouter_key:
                    provider = "openrouter"
                    target_model = f"anthropic/{model}" if "/" not in model else model
                    async for chunk in self._stream_openai_compatible(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        key=self.openrouter_key,
                        model=target_model,
                        system_prompt=system_prompt,
                        messages=messages,
                        temp=temperature,
                        max_tokens=max_tokens
                    ):
                        response_text += chunk
                        yield chunk
                else:
                    provider = "anthropic"
                    async for chunk in self._stream_anthropic(model, system_prompt, messages, temperature, max_tokens):
                        response_text += chunk
                        yield chunk

            else:
                # Other models (like gpt-*)
                if self.openrouter_key:
                    provider = "openrouter"
                    target_model = f"openai/{model}" if "/" not in model else model
                    async for chunk in self._stream_openai_compatible(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        key=self.openrouter_key,
                        model=target_model,
                        system_prompt=system_prompt,
                        messages=messages,
                        temp=temperature,
                        max_tokens=max_tokens
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
                        max_tokens=max_tokens
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
        self, url: str, key: Optional[str], model: str, system_prompt: str, messages: List[Dict[str, str]], temp: float, max_tokens: int
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

        formatted_messages = [{"role": "system", "content": system_prompt}] + messages

        payload = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temp,
            "max_tokens": max_tokens,
            "stream": True
        }

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
            prompt_chars = len(system_prompt) + sum(len(m.get("content", "")) for m in messages)
            prompt_tokens = int(prompt_chars / 4)
            completion_tokens = int(len(response_text) / 4)
            total_tokens = prompt_tokens + completion_tokens

            # Pricing mappings (per 1M tokens)
            pricing = {
                "gpt-4o-mini": (0.15, 0.60),
                "gpt-4o": (2.50, 10.00),
                "o4-mini": (1.15, 4.50),
                "claude-sonnet-4": (3.00, 15.00),
                "claude-opus-4": (15.00, 75.00),
                "claude-3-5-sonnet-20241022": (3.00, 15.00),
                "gemini-2.0-flash": (0.075, 0.30),
                "gemini-2.5-pro": (1.25, 5.00),
            }

            rate_in, rate_out = pricing.get(model, (0.0, 0.0))
            if "free" in model.lower() and provider in ["openrouter", "nvidia", "ollama"]:
                rate_in, rate_out = 0.0, 0.0

            cost = (prompt_tokens * rate_in + completion_tokens * rate_out) / 1_000_000

            from core.memory.database import async_session
            from core.memory.models import TokenUsage
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
                await session.commit()
        except Exception as e:
            print(f"✗ [Router] Token usage tracking failed: {e}")

    # ================================================================
    # Anthropic (Claude)
    # ================================================================

    async def _stream_anthropic(
        self, model: str, system_prompt: str, messages: List[Dict[str, str]], temp: float, max_tokens: int
    ) -> AsyncGenerator[str, None]:
        if not self.anthropic_key:
            yield "[Router Error: ANTHROPIC_API_KEY is not configured in the backend environment.]"
            return

        headers = {
            "x-api-key": self.anthropic_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        payload = {
            "model": model,
            "system": system_prompt,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tokens,
            "stream": True
        }

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
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

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

        async with httpx.AsyncClient(timeout=90.0) as client:
            try:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        yield f"[Gemini API Error {response.status_code}: {err_body.decode('utf-8')[:500]}]"
                        return

                    async for line in response.iter_lines():
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
                async with httpx.AsyncClient(timeout=90.0) as client:
                    async with client.stream("POST", url, headers=headers, json=payload) as response:
                        if response.status_code == 429:
                            # Rate limited — backoff and retry
                            wait = (2 ** attempt) * 2
                            print(f"⚠️ [Router] Rate limited (429). Retrying in {wait}s... (attempt {attempt+1}/{max_retries})")
                            await asyncio.sleep(wait)
                            continue

                        if response.status_code >= 500:
                            wait = (2 ** attempt) * 1
                            print(f"⚠️ [Router] Server error ({response.status_code}). Retrying in {wait}s...")
                            await asyncio.sleep(wait)
                            continue

                        if response.status_code != 200:
                            err_body = await response.aread()
                            yield f"[API Error {response.status_code}: {err_body.decode('utf-8')[:500]}]"
                            return

                        async for line in response.iter_lines():
                            if not line.startswith("data:"):
                                continue
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                text = self._extract_text_from_sse(data, parse_format)
                                if text:
                                    yield text
                            except json.JSONDecodeError:
                                continue
                        return  # Success — don't retry

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                wait = (2 ** attempt) * 1
                if attempt < max_retries - 1:
                    print(f"⚠️ [Router] Connection error: {e}. Retrying in {wait}s... (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait)
                else:
                    yield f"[Router Connection Error after {max_retries} retries: {str(e)}]"
            except Exception as e:
                yield f"[Router Exception: {str(e)}]"
                return

    @staticmethod
    def _extract_text_from_sse(data: dict, parse_format: str) -> str:
        """Extracts text content from an SSE data payload."""
        if parse_format == "anthropic":
            if data.get("type") == "content_block_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    return delta.get("text", "")
        elif parse_format == "openai":
            choices = data.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                return delta.get("content", "")
        return ""

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

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers=headers,
                    json=payload
                )
                if response.status_code == 200:
                    data = response.json()
                    return data["data"][0]["embedding"]
                else:
                    print(f"✗ [Router] OpenAI Embeddings error: {response.text[:200]}")
                    return None
            except Exception as e:
                print(f"✗ [Router] OpenAI Embeddings connection error: {str(e)}")
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

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=payload)
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
                    print(f"✗ [Router] Gemini Embeddings error: {response.text[:200]}")
                    return None
            except Exception as e:
                print(f"✗ [Router] Gemini Embeddings connection error: {str(e)}")
                return None


    # Alias for compatibility with older code paths
    get_embedding = generate_embeddings


# Global singleton router
llm_router = MultiModelRouter()

