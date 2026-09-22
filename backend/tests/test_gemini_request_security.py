import json

import httpx
import pytest

from core.llm.multi_model_router import MultiModelRouter


@pytest.mark.asyncio
async def test_gemini_requests_authenticate_with_header_not_query_string():
    secret = "secret-google-key"
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith(":streamGenerateContent"):
            payload = {"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]}
            return httpx.Response(200, text=f"data: {json.dumps(payload)}\n\n")
        if request.url.path.endswith(":generateContent"):
            return httpx.Response(
                200,
                json={
                    "candidates": [{
                        "content": {"parts": [{"text": "Hello"}]},
                        "finishReason": "STOP",
                    }]
                },
            )
        if request.url.path.endswith(":embedContent"):
            return httpx.Response(200, json={"embedding": {"values": [1.0, 2.0]}})
        return httpx.Response(404)

    router = MultiModelRouter()
    await router._http_client.aclose()
    router.gemini_key = secret
    router._http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))

    try:
        chunks = [chunk async for chunk in router._stream_gemini(
            "gemini-3.6-flash", "Be helpful", [{"role": "user", "content": "Hi"}], 0.2, 64
        )]
        events = [event async for event in router._gemini_tool_stream(
            "gemini-3.6-flash", "Be helpful", [{"role": "user", "content": "Hi"}], [], 0.2, 64
        )]
        embedding = await router._embeddings_gemini("Hi")
    finally:
        await router.aclose()

    assert chunks == ["Hello"]
    assert any(event.get("delta") == "Hello" for event in events)
    assert embedding is not None
    assert len(requests) == 3
    for request in requests:
        assert secret not in str(request.url)
        assert "key" not in request.url.params
        assert request.headers["x-goog-api-key"] == secret
