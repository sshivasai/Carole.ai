import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from core.llm.provider_sync import (
    _merge_provider_models,
    fetch_openrouter_models,
    fetch_openai_models,
    fetch_google_models,
    fetch_ollama_models,
    sync_all_provider_models,
)
from core.llm.model_catalog import _validate_model_catalog, load_model_catalog


def test_merge_provider_models_preserves_special():
    existing = [
        {"value": "openrouter/auto", "label": "Auto", "special": True},
        {"value": "openrouter/free", "label": "Free", "special": True},
        {"value": "openrouter/custom/my-model", "label": "My Custom Model"},
    ]
    fetched = [
        {"value": "openrouter/anthropic/claude-3.7-sonnet", "label": "Claude 3.7 Sonnet"},
        {"value": "openrouter/custom/my-model", "label": "My Custom Model (Fetched)"},
    ]

    merged = _merge_provider_models(existing, fetched, "openrouter")

    # openrouter/auto and openrouter/free must be preserved first
    assert merged[0]["value"] == "openrouter/auto"
    assert merged[0]["special"] is True
    assert merged[1]["value"] == "openrouter/free"
    assert merged[1]["special"] is True

    values = [m["value"] for m in merged]
    # No duplicate entries
    assert values.count("openrouter/custom/my-model") == 1
    assert "openrouter/anthropic/claude-3.7-sonnet" in values


def test_google_merge_prunes_models_missing_from_discovery():
    existing = [
        {"value": "gemini-2.0-flash", "label": "Retired"},
        {"value": "gemini-3.6-flash", "label": "Current"},
    ]
    fetched = [
        {"value": "gemini-3.8-flash", "label": "Gemini 3.8 Flash"},
    ]

    merged = _merge_provider_models(existing, fetched, "google")

    assert [entry["value"] for entry in merged] == ["gemini-3.8-flash"]


@pytest.mark.asyncio
async def test_fetch_openai_models_filters():
    mock_response = {
        "data": [
            {"id": "gpt-4o"},
            {"id": "o3"},
            {"id": "text-embedding-3-small"},
            {"id": "whisper-1"},
            {"id": "dall-e-3"},
            {"id": "o4-mini"},
        ]
    }

    from unittest.mock import MagicMock
    mock_client = AsyncMock()
    mock_res = MagicMock()
    mock_res.json.return_value = mock_response
    mock_res.raise_for_status.return_value = None
    mock_client.get.return_value = mock_res

    models = await fetch_openai_models(mock_client, "fake-key")

    values = [m["value"] for m in models]
    assert "gpt-4o" in values
    assert "o3" in values
    assert "o4-mini" in values
    # Excluded non-chat models
    assert "text-embedding-3-small" not in values
    assert "whisper-1" not in values
    assert "dall-e-3" not in values


@pytest.mark.asyncio
async def test_fetch_google_models_keeps_api_key_out_of_url():
    from unittest.mock import MagicMock

    mock_client = AsyncMock()
    mock_res = MagicMock()
    mock_res.json.return_value = {
        "models": [{
            "name": "models/gemini-3.6-flash",
            "displayName": "Gemini 3.6 Flash",
            "supportedGenerationMethods": ["generateContent"],
        }]
    }
    mock_res.raise_for_status.return_value = None
    mock_client.get.return_value = mock_res

    models = await fetch_google_models(mock_client, "secret-google-key")

    assert models[0]["value"] == "gemini-3.6-flash"
    request_url = mock_client.get.await_args.args[0]
    request_headers = mock_client.get.await_args.kwargs["headers"]
    assert "secret-google-key" not in request_url
    assert request_headers["x-goog-api-key"] == "secret-google-key"


@pytest.mark.asyncio
async def test_sync_all_provider_models_smoke():
    summary = await sync_all_provider_models()
    assert summary["status"] == "ok"
    assert summary["total_models"] > 0
    # openrouter should sync because it uses public endpoint
    assert "openrouter" in summary["synced_providers"]

    # Verify catalog is valid
    catalog = load_model_catalog()
    _validate_model_catalog(catalog)
    assert "openrouter" in catalog
    assert len(catalog["openrouter"]["models"]) > 5


@pytest.mark.asyncio
async def test_sync_endpoint(client, monkeypatch):
    from tests.test_advanced_features import create_authenticated_user
    headers, owner_id, _ = await create_authenticated_user(client, "modelsync@carole.ai")
    monkeypatch.setenv("CAROLE_OWNER_ID", owner_id)
    res = await client.post("/api/models/sync", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["total_models"] > 0
    assert "openrouter" in data["synced_providers"]

