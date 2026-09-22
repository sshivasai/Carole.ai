from unittest.mock import AsyncMock
from types import SimpleNamespace
import json
import httpx

import pytest

from core.llm.multi_model_router import (
    MultiModelRouter, LLMProviderError, ERROR_MODEL_NOT_FOUND, normalize_model_id,
)


@pytest.mark.parametrize("model,expected", [
    (" openai/gpt-4o ", "gpt-4o"),
    ("anthropic/claude-test", "claude-test"),
    ("google/gemini-test", "gemini-test"),
    ("openrouter/openai/gpt-4o", "openrouter/openai/gpt-4o"),
    ("nvidia/meta/llama", "nvidia/meta/llama"),
    ("ollama/llama3", "ollama/llama3"),
])
def test_model_aliases(model, expected):
    assert normalize_model_id(model) == expected


def test_invalid_model_is_not_an_outage():
    error = LLMProviderError.classify_http_error(
        400, '{"error":{"message":"invalid model ID"}}', "openai", "gpt-4o"
    )
    assert error.error_type == ERROR_MODEL_NOT_FOUND
    assert "unreachable" not in error.action_hint


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["text", "tools", "reasoning"])
async def test_openai_alias_in_all_streams(mode):
    router = MultiModelRouter()
    router.openai_key = "test-key"
    router._log_usage = AsyncMock()
    captured = []
    await router._http_client.aclose()

    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"OK"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')

    router._http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))

    async def capture(*args, **kwargs):
        payload = kwargs.get("payload")
        if payload is None:
            payload = next(arg for arg in args if isinstance(arg, dict) and "model" in arg)
        captured.append(payload)
        if False:
            yield

    router._stream_with_retry = capture
    router._stream_with_retry_rich = capture
    try:
        if mode == "text":
            stream = router.generate_stream("openai/gpt-4o", "", [])
        elif mode == "tools":
            stream = router.generate_with_tools("openai/gpt-4o", "", [], [])
        else:
            stream = router.generate_stream_with_reasoning("openai/gpt-4o", "", [], reasoning_effort="low")
        async for _ in stream:
            pass
        assert captured and all(p["model"] == "gpt-4o" for p in captured)
    finally:
        await router.aclose()


def test_agent_default_resolves_after_settings_change(monkeypatch):
    from core.api.crud_routes import AgentCreate
    import core.config
    monkeypatch.setattr(core.config, "DEFAULT_FAST_MODEL", "gpt-4o-mini")
    assert AgentCreate(team_id="test", name="Agent", role="Coder").model == "gpt-4o-mini"
    monkeypatch.setattr(core.config, "DEFAULT_FAST_MODEL", "gemini-test")
    assert AgentCreate(team_id="test", name="Agent", role="Coder").model == "gemini-test"


@pytest.mark.asyncio
@pytest.mark.parametrize("change,expected", [({}, "gpt-4o"), ({"fallback_model": None}, None), ({"fallback_model": ""}, None), ({"model": "gemini-test"}, "gpt-4o")])
async def test_model_settings_update(monkeypatch, change, expected):
    from core.api import crud_routes
    from core.chat.event_bus import event_bus
    from core.chat.message_router import message_router
    agent = SimpleNamespace(id="agent", team_id="team", name="Archer", role="Coder",
        model="gpt-4o-mini", fallback_model="gpt-4o", reasoning_effort="none",
        personality="professional", skills=[], custom_instructions=None,
        tool_permissions={}, auto_approve_plans=False)
    monkeypatch.setattr(crud_routes, "_assert_agent_access", AsyncMock(return_value=agent))
    monkeypatch.setattr(crud_routes, "_get_human_name", AsyncMock(return_value="Owner"))
    monkeypatch.setattr(event_bus, "publish", AsyncMock())
    monkeypatch.setattr(message_router, "route_message", AsyncMock())
    db = SimpleNamespace(commit=AsyncMock())
    result = await crud_routes.update_agent("agent", crud_routes.AgentUpdate(**change), db, {"sub": "owner"})
    assert result["fallback_model"] == expected
    assert result["model"] == change.get("model", "gpt-4o-mini")
    db.commit.assert_awaited_once()
