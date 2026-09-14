"""
# backend/core/llm/provider_sync.py

Dynamic LLM Provider Model Synchronization Service.

Queries active provider APIs (OpenRouter, OpenAI, Anthropic, Google Gemini, Ollama, Groq, DeepSeek)
to discover all available and newly released models, and persists them into the user's
supported_models catalog (~/.carole/supported_models.json) while preserving the exact schema.

Schema:
{
  "provider_id": {
    "label": "Provider Display Name",
    "key_name": "API_KEY_NAME",
    "models": [
      {
        "value": "model_id",
        "label": "Model Display Name",
        "special": bool (optional)
      }
    ]
  }
}
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
import httpx

from core.llm.config_manager import load_config, get_key
from core.llm.model_catalog import (
    load_model_catalog,
    save_model_catalog,
    _validate_model_catalog,
)

logger = logging.getLogger("carole.provider_sync")

# Default HTTP timeout for model discovery calls (short so startup is never delayed)
DEFAULT_DISCOVERY_TIMEOUT = 8.0


async def fetch_openrouter_models(client: httpx.AsyncClient, api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetch all available models from OpenRouter (public endpoint, works with or without key).
    Returns formatted model entries: { "value": "openrouter/<id>", "label": "<name>" }.
    """
    headers = {
        "HTTP-Referer": "https://carole.ai",
        "X-Title": "Carole.ai",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    resp = await client.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=DEFAULT_DISCOVERY_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    items = payload.get("data", [])

    results: List[Dict[str, Any]] = []
    for item in items:
        model_id = item.get("id")
        if not model_id:
            continue

        raw_name = item.get("name") or model_id
        pricing = item.get("pricing") or {}
        prompt_cost = pricing.get("prompt")
        completion_cost = pricing.get("completion")

        # Mark free models
        is_free = (prompt_cost == "0" and completion_cost == "0") or ":free" in model_id
        suffix = " (FREE)" if is_free else ""

        results.append({
            "value": f"openrouter/{model_id}",
            "label": f"{raw_name}{suffix}",
        })

    return results


async def fetch_openai_models(client: httpx.AsyncClient, api_key: str) -> List[Dict[str, Any]]:
    """
    Fetch chat/reasoning models from OpenAI's /v1/models endpoint.
    Filters out non-chat models (audio, moderation, tts, embeddings, dall-e).
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = await client.get("https://api.openai.com/v1/models", headers=headers, timeout=DEFAULT_DISCOVERY_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    items = payload.get("data", [])

    # Prefixes / patterns of chat & reasoning models we support
    allowed_prefixes = ("gpt-", "o1", "o3", "o4", "chatgpt-")
    excluded_keywords = ("audio", "realtime", "transcribe", "tts", "whisper", "moderation", "embedding", "dall-e", "search-", "similarity-")

    results: List[Dict[str, Any]] = []
    for item in items:
        m_id = item.get("id", "")
        if not m_id:
            continue
        m_lower = m_id.lower()

        if any(exc in m_lower for exc in excluded_keywords):
            continue

        if any(m_lower.startswith(pref) for pref in allowed_prefixes):
            results.append({
                "value": m_id,
                "label": m_id,
            })

    # Sort so top models appear first (e.g. o3, o4, gpt-4o, gpt-5)
    def _rank(m: Dict[str, Any]) -> int:
        v = m["value"].lower()
        if "gpt-5" in v: return 0
        if "o3" in v: return 1
        if "o4" in v: return 2
        if "gpt-4o" in v: return 3
        if "o1" in v: return 4
        return 10

    results.sort(key=_rank)
    return results


async def fetch_anthropic_models(client: httpx.AsyncClient, api_key: str) -> List[Dict[str, Any]]:
    """
    Fetch models from Anthropic API (GET /v1/models).
    """
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    resp = await client.get("https://api.anthropic.com/v1/models", headers=headers, timeout=DEFAULT_DISCOVERY_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    items = payload.get("data", [])

    results: List[Dict[str, Any]] = []
    for item in items:
        m_id = item.get("id")
        if not m_id:
            continue
        label = item.get("display_name") or m_id
        results.append({
            "value": m_id,
            "label": label,
        })
    return results


async def fetch_google_models(client: httpx.AsyncClient, api_key: str) -> List[Dict[str, Any]]:
    """
    Fetch models from Google Gemini API (GET /v1beta/models).
    Filters for models that support generateContent.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    resp = await client.get(url, timeout=DEFAULT_DISCOVERY_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    items = payload.get("models", [])

    results: List[Dict[str, Any]] = []
    for item in items:
        methods = item.get("supportedGenerationMethods", [])
        if "generateContent" not in methods:
            continue
        name = item.get("name", "")
        clean_val = name.replace("models/", "", 1)
        disp = item.get("displayName") or clean_val
        results.append({
            "value": clean_val,
            "label": f"{disp} ({clean_val})",
        })
    return results


async def fetch_ollama_models(client: httpx.AsyncClient, base_url: str = "http://localhost:11434") -> List[Dict[str, Any]]:
    """
    Fetch locally installed models from Ollama /api/tags endpoint.
    """
    clean_url = base_url.rstrip("/")
    if clean_url.endswith("/v1"):
        clean_url = clean_url[:-3]

    url = f"{clean_url}/api/tags"
    resp = await client.get(url, timeout=3.0)
    resp.raise_for_status()
    payload = resp.json()
    items = payload.get("models", [])

    results: List[Dict[str, Any]] = []
    for item in items:
        tag = item.get("name")
        if not tag:
            continue
        results.append({
            "value": f"ollama/{tag}",
            "label": f"{tag} (local)",
        })
    return results


async def fetch_groq_models(client: httpx.AsyncClient, api_key: str) -> List[Dict[str, Any]]:
    """
    Fetch models from Groq API (GET /openai/v1/models).
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = await client.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=DEFAULT_DISCOVERY_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    items = payload.get("data", [])

    results: List[Dict[str, Any]] = []
    for item in items:
        m_id = item.get("id")
        if not m_id:
            continue
        results.append({
            "value": f"groq/{m_id}",
            "label": f"{m_id} (Groq)",
        })
    return results


async def fetch_deepseek_models(client: httpx.AsyncClient, api_key: str) -> List[Dict[str, Any]]:
    """
    Fetch models from DeepSeek API (GET /models).
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = await client.get("https://api.deepseek.com/models", headers=headers, timeout=DEFAULT_DISCOVERY_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    items = payload.get("data", [])

    results: List[Dict[str, Any]] = []
    for item in items:
        m_id = item.get("id")
        if not m_id:
            continue
        results.append({
            "value": m_id,
            "label": f"DeepSeek {m_id}",
        })
    return results


def _merge_provider_models(
    existing_models: List[Dict[str, Any]],
    fetched_models: List[Dict[str, Any]],
    provider_id: str,
) -> List[Dict[str, Any]]:
    """
    Intelligently merges fetched models into existing models list:
    1. Preserves special routing entries (e.g. openrouter/auto, openrouter/free) at index 0 and 1.
    2. Keeps existing custom models that the user manually defined.
    3. Merges newly fetched models without duplicates.
    """
    merged: List[Dict[str, Any]] = []
    seen_values = set()

    # 1. Special entries always go first
    for m in existing_models:
        if m.get("special"):
            merged.append(m)
            seen_values.add(m.get("value"))

    # If provider is openrouter and special models were missing, add defaults
    if provider_id == "openrouter":
        if "openrouter/auto" not in seen_values:
            merged.insert(0, {
                "value": "openrouter/auto",
                "label": "⚡ Auto — NotDiamond best model",
                "special": True,
            })
            seen_values.add("openrouter/auto")
        if "openrouter/free" not in seen_values:
            merged.insert(1, {
                "value": "openrouter/free",
                "label": "🆓 Auto Free — random free model",
                "special": True,
            })
            seen_values.add("openrouter/free")

    # 2. Add fetched models (fresh and official)
    for m in fetched_models:
        val = m.get("value")
        if val and val not in seen_values:
            merged.append(m)
            seen_values.add(val)

    # 3. Retain any existing models that were not in fetched (user-defined or custom entries)
    for m in existing_models:
        val = m.get("value")
        if val and val not in seen_values:
            merged.append(m)
            seen_values.add(val)

    return merged


async def sync_all_provider_models() -> Dict[str, Any]:
    """
    Coordinates model discovery across all providers.
    Updates the catalog in ~/.carole/supported_models.json atomically.
    Returns a summary dict with sync details.
    """
    cfg = load_config()
    current_catalog = load_model_catalog()

    openrouter_key = get_key(cfg, "openrouter", "OPENROUTER_API_KEY")
    openai_key = get_key(cfg, "openai", "OPENAI_API_KEY")
    anthropic_key = get_key(cfg, "anthropic", "ANTHROPIC_API_KEY")
    google_key = get_key(cfg, "google", "GOOGLE_API_KEY") or get_key(cfg, "google", "GEMINI_API_KEY")
    groq_key = get_key(cfg, "groq", "GROQ_API_KEY")
    deepseek_key = get_key(cfg, "deepseek", "DEEPSEEK_API_KEY")
    ollama_url = cfg.get("providers", {}).get("ollama_base_url", "http://localhost:11434")

    tasks: Dict[str, asyncio.Task] = {}
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # OpenRouter (public endpoint, works with or without key)
        tasks["openrouter"] = asyncio.create_task(fetch_openrouter_models(client, openrouter_key))

        if openai_key:
            tasks["openai"] = asyncio.create_task(fetch_openai_models(client, openai_key))

        if anthropic_key:
            tasks["anthropic"] = asyncio.create_task(fetch_anthropic_models(client, anthropic_key))

        if google_key:
            tasks["google"] = asyncio.create_task(fetch_google_models(client, google_key))

        if groq_key:
            tasks["groq"] = asyncio.create_task(fetch_groq_models(client, groq_key))

        if deepseek_key:
            tasks["deepseek"] = asyncio.create_task(fetch_deepseek_models(client, deepseek_key))

        # Ollama local check
        tasks["ollama"] = asyncio.create_task(fetch_ollama_models(client, ollama_url))

        # Await all tasks concurrently with exception handling
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    synced_providers: List[str] = []
    errors: Dict[str, str] = {}

    for provider_id, res in zip(tasks.keys(), results):
        if isinstance(res, Exception):
            logger.debug("Provider '%s' sync skipped or failed: %s", provider_id, res)
            errors[provider_id] = str(res)
            continue

        if isinstance(res, list) and res:
            if provider_id not in current_catalog:
                default_labels = {
                    "openrouter": "OpenRouter",
                    "openai": "OpenAI",
                    "anthropic": "Anthropic",
                    "google": "Google Gemini",
                    "ollama": "Ollama (local)",
                    "groq": "Groq",
                    "deepseek": "DeepSeek",
                }
                current_catalog[provider_id] = {
                    "label": default_labels.get(provider_id, provider_id.title()),
                    "key_name": None if provider_id == "ollama" else provider_id,
                    "models": [],
                }

            existing_list = current_catalog[provider_id].get("models", [])
            merged = _merge_provider_models(existing_list, res, provider_id)
            current_catalog[provider_id]["models"] = merged
            synced_providers.append(provider_id)
            logger.info("✓ Synced %d models for provider '%s'", len(merged), provider_id)

    # Validate and atomically save
    try:
        _validate_model_catalog(current_catalog)
        save_model_catalog(current_catalog)
        logger.info("Successfully saved dynamically synced model catalog.")
    except Exception as exc:
        logger.error("Failed to save synced model catalog: %s", exc)
        errors["save"] = str(exc)

    total_models = sum(len(p.get("models", [])) for p in current_catalog.values())

    return {
        "status": "ok",
        "synced_providers": synced_providers,
        "total_models": total_models,
        "errors": errors,
        "catalog": current_catalog,
    }


async def sync_provider_models_background() -> None:
    """
    Background worker invoked during app startup.
    Runs non-blocking, logs results, suppresses errors so server startup is uninterrupted.
    """
    logger.info("🔄 [ModelSync] Starting background provider model synchronization...")
    try:
        summary = await sync_all_provider_models()
        logger.info(
            "✓ [ModelSync] Completed! Synced providers: %s (Total models in catalog: %d)",
            ", ".join(summary.get("synced_providers", [])) or "None",
            summary.get("total_models", 0),
        )
    except Exception as exc:
        logger.warning("⚠ [ModelSync] Background sync encountered an error: %s", exc)
