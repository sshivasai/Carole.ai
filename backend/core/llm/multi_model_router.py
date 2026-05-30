"""
# backend/core/llm/multi_model_router.py

This module acts as the gateway to route LLM requests to different providers.

Supported Providers:
1. Anthropic (Claude models e.g. claude-3-5-sonnet)
2. OpenAI (GPT models e.g. gpt-4o, gpt-4o-mini)
3. Qwen (Via DashScope, OpenRouter, or local vLLM/Ollama OpenAI-compatible endpoint)

Features:
- Standard generation completions.
- Asynchronous generator streaming (crucial for live-streaming agent thoughts to the WebSocket EventBus).
- Dynamic fallback or base-URL configuration for local LLMs.
"""

import os
import json
import httpx
from typing import AsyncGenerator, List, Dict

class MultiModelRouter:
    def __init__(self):
        # Load API keys and configurations
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        
        # Qwen specific configuration (defaults to OpenAI-compatible base URL if local)
        self.qwen_key = os.getenv("QWEN_API_KEY")
        self.qwen_base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    async def generate_completion(
        self, 
        model: str, 
        system_prompt: str, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7,
        max_tokens: int = 4000
    ) -> str:
        """
        Generates a standard non-streaming text completion.
        """
        response_text = ""
        async for chunk in self.generate_stream(model, system_prompt, messages, temperature, max_tokens):
            response_text += chunk
        return response_text

    async def generate_stream(
        self, 
        model: str, 
        system_prompt: str, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7,
        max_tokens: int = 4000
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronous generator streaming chunks of the completion in real-time.
        """
        # 1. Route to Anthropic (Claude)
        if model.startswith("claude"):
            async for chunk in self._stream_anthropic(model, system_prompt, messages, temperature, max_tokens):
                yield chunk

        # 2. Route to OpenAI (GPT)
        elif model.startswith("gpt"):
            async for chunk in self._stream_openai(model, system_prompt, messages, temperature, max_tokens):
                yield chunk

        # 3. Route to Qwen (Or other OpenAI compatible endpoints like Ollama)
        elif model.startswith("qwen"):
            async for chunk in self._stream_qwen(model, system_prompt, messages, temperature, max_tokens):
                yield chunk

        else:
            raise ValueError(f"Unsupported model router target: '{model}'")

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

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                async with client.stream(
                    "POST", 
                    "https://api.anthropic.com/v1/messages", 
                    headers=headers, 
                    json=payload
                ) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        yield f"[Anthropic API Error {response.status_code}: {err_body.decode('utf-8')}]"
                        return

                    async for line in response.iter_lines():
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                # Anthropic uses 'content_block_delta' for message chunk streams
                                if data.get("type") == "content_block_delta":
                                    delta = data.get("delta", {})
                                    if delta.get("type") == "text_delta":
                                        yield delta.get("text", "")
                            except json.JSONDecodeError:
                                continue
            except Exception as e:
                yield f"[Router Connection Exception: {str(e)}]"

    async def _stream_openai(
        self, model: str, system_prompt: str, messages: List[Dict[str, str]], temp: float, max_tokens: int
    ) -> AsyncGenerator[str, None]:
        if not self.openai_key:
            yield "[Router Error: OPENAI_API_KEY is not configured in the backend environment.]"
            return

        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json"
        }

        # Formulate full payload including system prompt as first message
        formatted_messages = [{"role": "system", "content": system_prompt}] + messages
        
        payload = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temp,
            "max_tokens": max_tokens,
            "stream": True
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                async with client.stream(
                    "POST", 
                    "https://api.openai.com/v1/chat/completions", 
                    headers=headers, 
                    json=payload
                ) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        yield f"[OpenAI API Error {response.status_code}: {err_body.decode('utf-8')}]"
                        return

                    async for line in response.iter_lines():
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                choices = data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue
            except Exception as e:
                yield f"[Router Connection Exception: {str(e)}]"

    async def _stream_qwen(
        self, model: str, system_prompt: str, messages: List[Dict[str, str]], temp: float, max_tokens: int
    ) -> AsyncGenerator[str, None]:
        # Qwen can run locally (no keys) or via DashScope/OpenRouter (requires keys)
        headers = {"Content-Type": "application/json"}
        if self.qwen_key:
            headers["Authorization"] = f"Bearer {self.qwen_key}"

        formatted_messages = [{"role": "system", "content": system_prompt}] + messages
        
        payload = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temp,
            "max_tokens": max_tokens,
            "stream": True
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                async with client.stream(
                    "POST", 
                    f"{self.qwen_base_url}/chat/completions", 
                    headers=headers, 
                    json=payload
                ) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        yield f"[Qwen API Error {response.status_code}: {err_body.decode('utf-8')}]"
                        return

                    async for line in response.iter_lines():
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                choices = data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue
            except Exception as e:
                yield f"[Router Connection Exception: {str(e)}]"

    async def generate_embeddings(self, text: str) -> List[float]:
        """
        Generates a 1536-dimensional vector embedding for the input text using OpenAI.
        """
        if not self.openai_key:
            # Return a mock zero-vector if no OpenAI key is configured
            return [0.0] * 1536

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
                    print(f"✗ [Router] Embeddings API error: {response.text}")
                    return [0.0] * 1536
            except Exception as e:
                print(f"✗ [Router] Embeddings connection error: {str(e)}")
                return [0.0] * 1536

# Global singleton router
llm_router = MultiModelRouter()
