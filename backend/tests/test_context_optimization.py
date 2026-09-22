"""Behavioral regression corpus for context budgets, accounting and loop recovery."""
import asyncio
import json
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from core.agent.context_compiler import (
    CHAT, WORK, ContextCapacityError, compile_request, count_tokens,
    select_policy, select_schemas, provider_schemas, budget_records,
)
from core.agent.loop_policy import LoopGuard, cancellable_events
from core.agent.message_history import MessageHistory
from core.tools.context import CancellationToken
from core.llm.usage_accounting import normalize_usage
from core.llm.multi_model_router import MultiModelRouter, LLMProviderError


@pytest.mark.parametrize("prompt", ["hi @Archer", "What are your capabilities?", "what can you do ?", "hello"])
def test_small_talk_profile(prompt):
    assert select_policy(prompt, "orchestrator") == CHAT


@pytest.mark.parametrize("prompt", ["Hi Archer, implement the API", "what can you do with this file?", "hello; delete everything", "continue", "review the patch"])
def test_ambiguous_or_action_requests_keep_capabilities(prompt):
    assert select_policy(prompt, "orchestrator") != CHAT


def test_attachments_and_worker_tasks_never_use_greeting_profile():
    assert select_policy("hi", attachments=True) != CHAT
    assert select_policy("hi", task_id="task") != CHAT


def test_preflight_preserves_inputs_and_reserves_output():
    messages = [{"role": "user", "content": "Do not change the public API."}]
    before = json.dumps(messages)
    plan = compile_request("policy", messages, [], model="gpt-4o", context_window=4096, policy=CHAT)
    assert plan.estimated_tokens + plan.output_reserve + plan.uncertainty_reserve <= 4096
    assert plan.estimated_tokens == sum(plan.components.values())
    assert json.dumps(messages) == before
    with pytest.raises(ContextCapacityError):
        compile_request("policy", [{"role": "user", "content": "required " * 10000}], [], model="gpt-4o", context_window=4096)


def test_media_is_reserved_without_counting_base64_as_prose():
    messages = [{"role": "user", "content": [{"type": "image", "source": {"data": "A" * 200000}}]}]
    plan = compile_request("", messages, [], model="gpt-4o", context_window=16000)
    assert plan.components["media"] == 4096
    assert plan.components["messages"] < 100


def test_discovery_and_requested_schema_are_never_cut():
    tools = [{"type": "function", "function": {"name": n, "description": "x " * 500,
             "parameters": {"type": "object", "properties": {}}}}
             for n in ["edit_file", "fetch_tool_schemas", "special"]]
    chosen = select_schemas(tools, 10, "gpt-4o", required={"special"})
    assert [x["function"]["name"] for x in chosen] == ["fetch_tool_schemas", "special"]
    assert all(x in tools for x in chosen)
    anthropic = provider_schemas(chosen, "anthropic")
    google = provider_schemas(anthropic, "google")
    assert provider_schemas(google, "openai") == chosen


def test_memory_budget_deduplicates_and_prefers_relevant_whole_records():
    records = ["unrelated " * 200, "auth uses signed sessions", "auth uses signed sessions"]
    result = budget_records(records, 20, "auth sessions", "gpt-4o")
    assert result == records[1]


@pytest.mark.parametrize("raw,input_count,output,reads,writes,reasoning", [
    ({"prompt_tokens": 100, "completion_tokens": 20, "prompt_tokens_details": {"cached_tokens": 80}, "completion_tokens_details": {"reasoning_tokens": 10}}, 100, 20, 80, None, 10),
    ({"input_tokens": 10, "cache_read_input_tokens": 80, "cache_creation_input_tokens": 10, "output_tokens": 20}, 100, 20, 80, 10, None),
    ({"input_tokens": 100, "input_tokens_details": {"cached_tokens": 80}, "output_tokens": 20}, 100, 20, 80, None, None),
])
def test_usage_subsets_not_double_counted(raw, input_count, output, reads, writes, reasoning):
    value = normalize_usage(raw)
    assert (value.prompt_tokens, value.completion_tokens, value.cache_read_tokens, value.cache_write_tokens, value.reasoning_tokens) == (input_count, output, reads, writes, reasoning)
    assert value.total_tokens == input_count + output


def test_partial_malformed_usage_retains_per_field_provenance():
    usage = normalize_usage({"prompt_tokens": True, "completion_tokens": 7, "prompt_tokens_details": "bad"}, 90, 3)
    assert usage.prompt_tokens == 90 and usage.input_source == "estimated"
    assert usage.completion_tokens == 7 and usage.output_source == "provider"
    assert usage.cache_read_tokens is None


def test_corrective_turns_are_bounded_independently():
    guard = LoopGuard()
    assert guard.allow_correction("truncation")
    assert guard.allow_correction("truncation")
    assert not guard.allow_correction("truncation")
    assert guard.allow_correction("empty")


@pytest.mark.asyncio
async def test_cancellation_interrupts_blocked_stream_and_closes_it():
    token = CancellationToken()
    entered, closed = asyncio.Event(), asyncio.Event()
    async def stream():
        try:
            entered.set()
            await asyncio.Event().wait()
            yield {}
        finally:
            closed.set()
    async def consume():
        async for _ in cancellable_events(stream(), token):
            pass
    task = asyncio.create_task(consume())
    await entered.wait()
    token.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    assert closed.is_set()


@pytest.mark.asyncio
async def test_stalled_stream_has_bounded_idle_timeout():
    async def stream():
        await asyncio.Event().wait()
        yield {}
    with pytest.raises(TimeoutError, match="stalled"):
        async for _ in cancellable_events(stream(), idle_timeout=0.01):
            pass


def test_signed_reasoning_survives_history_roundtrip():
    history = MessageHistory()
    history.add_user("work")
    blocks = [{"type": "thinking", "thinking": "internal", "signature": "provider-signature"}]
    history.add_assistant_text("", [{"id": "c1", "name": "read", "input": {}}], blocks)
    history.add_tool_results([{"tool_use_id": "c1", "content": "result"}])
    copied = MessageHistory(seed=history.get_messages()).get_messages()
    assert copied[1]["content"][0] == blocks[0]
    blocks[0]["signature"] = "changed"
    assert copied[1]["content"][0]["signature"] == "provider-signature"


@pytest.mark.asyncio
async def test_shared_budget_atomic_reservation_and_idempotent_settlement():
    from core.agent.run_budget import create_budget, reserve, settle, BudgetExceeded
    from core.memory.database import async_session
    from core.memory.models import RunTokenBudget
    run = str(uuid.uuid4())
    await create_budget(run, 100)
    calls = [str(uuid.uuid4()), str(uuid.uuid4())]
    outcomes = await asyncio.gather(*(reserve(run, call, 70) for call in calls), return_exceptions=True)
    assert sum(isinstance(value, BudgetExceeded) for value in outcomes) == 1
    winner = calls[next(i for i, value in enumerate(outcomes) if value is None)]
    await settle(winner, 40)
    await settle(winner, 1)
    async with async_session() as db:
        row = await db.get(RunTokenBudget, run)
        assert row.spent == 40 and row.reserved == 0


@pytest.mark.asyncio
async def test_router_fallback_is_bounded_and_does_not_replay_partial_output(monkeypatch):
    router = MultiModelRouter()
    router.openai_key = "test"
    router._log_usage = AsyncMock()
    calls = []
    async def fail(*args, **kwargs):
        calls.append(args[2])
        if False:
            yield {}
        raise LLMProviderError("provider_unavailable", "openai", args[2])
    router._openai_tool_stream = fail
    try:
        with pytest.raises(LLMProviderError):
            async for _ in router.generate_with_tools("gpt-primary", "", [], [], fallback_model="gpt-secondary"):
                pass
        assert calls == ["gpt-primary", "gpt-secondary"]
        calls.clear()
        async def partial(*args, **kwargs):
            calls.append(args[2])
            yield {"type": "text_delta", "delta": "partial"}
            raise LLMProviderError("provider_unavailable", "openai", args[2])
        router._openai_tool_stream = partial
        with pytest.raises(LLMProviderError):
            async for _ in router.generate_with_tools("gpt-primary", "", [], [], fallback_model="gpt-secondary"):
                pass
        assert calls == ["gpt-primary"]
    finally:
        await router.aclose()


def test_artifact_dedup_search_and_scope(tmp_path, monkeypatch):
    from core.agent import observation_cache as cache
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    content = "start\n" + "unimportant\n" * 1000 + "FAILED auth_test: useful middle evidence\n" + "other\n" * 1000
    first = cache.cache_observation("test", content, "team:agent")
    second = cache.cache_observation("test", content, "team:agent")
    artifacts = list(tmp_path.rglob("*.txt"))
    assert len(artifacts) == 1 and first == second
    assert "FAILED auth_test" in first
    assert "FAILED auth_test" in cache.read_observation(artifacts[0].name, "team:agent", query="auth_test")
    with pytest.raises(FileNotFoundError):
        cache.read_observation(artifacts[0].name, "other:agent")


@pytest.mark.asyncio
async def test_coordinator_greeting_skips_memory_and_board_queries(owned_browser, db_session, monkeypatch):
    from core.memory.models import Agent, Team
    from core.agent.coordinator import CoordinatorAgent
    from core.prompts import build_agent_system_prompt
    from core.llm.multi_model_router import llm_router
    row = await db_session.get(Agent, uuid.UUID(owned_browser["agent_id"]))
    team = await db_session.get(Team, row.team_id)
    agent = CoordinatorAgent(str(row.id), str(team.id), str(team.project_id), "Archer", "orchestrator",
                             "gpt-4o-mini", build_agent_system_prompt("Archer", "orchestrator"))
    agent._context_policy = CHAT
    embedding = AsyncMock(side_effect=AssertionError("Chat must not embed"))
    monkeypatch.setattr(llm_router, "generate_embeddings", embedding)
    prompt = await agent.assemble_system_prompt(db_session, "what are your capabilities?")
    embedding.assert_not_called()
    assert "active task board" not in prompt
    assert count_tokens(prompt, "gpt-4o-mini") < 1500
    assert "INSTRUCTION PRIORITY" in prompt


@pytest.mark.asyncio
async def test_complete_greeting_run_accounts_one_request_and_rehydrates_ui(owned_browser, db_session, client, monkeypatch):
    from core.memory.models import Agent, Team, TokenUsage, RunTokenBudget
    from core.agent.coordinator import CoordinatorAgent
    from core.prompts import build_agent_system_prompt
    from core.llm.multi_model_router import llm_router
    row = await db_session.get(Agent, uuid.UUID(owned_browser["agent_id"]))
    team = await db_session.get(Team, row.team_id)
    row.name, row.role, row.model = "Archer", "orchestrator", "gpt-4o-mini"
    row.system_prompt = build_agent_system_prompt(row.name, row.role)
    await db_session.commit()
    payloads = []
    def respond(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, text='data: {"id":"req-test","model":"gpt-4o-mini","choices":[{"delta":{"content":"I can coordinate tasks and help with files."},"finish_reason":"stop"}],"usage":{"prompt_tokens":700,"completion_tokens":12,"prompt_tokens_details":{"cached_tokens":500}}}\n\ndata: [DONE]\n\n')
    transport = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(llm_router, "_http_client", transport)
    monkeypatch.setattr(llm_router, "openai_key", "test")
    embedding = AsyncMock(side_effect=AssertionError("No embedding on greetings"))
    monkeypatch.setattr(llm_router, "generate_embeddings", embedding)
    agent = CoordinatorAgent(str(row.id), str(team.id), str(team.project_id), row.name, row.role, row.model, row.system_prompt)
    try:
        await agent.run_loop(db_session, "what are your capabilities?")
    finally:
        await transport.aclose()
    embedding.assert_not_called()
    assert len(payloads) == 1
    assert payloads[0].get("tools", []) == [] and payloads[0]["max_tokens"] <= 512
    usage = await db_session.scalar(select(TokenUsage).where(TokenUsage.run_id == agent._run_id))
    assert usage.total_tokens == 712
    assert usage.accounting["cache_read_tokens"] == 500
    assert usage.accounting["estimated_tokens"] < 2000
    budget = await db_session.get(RunTokenBudget, usage.accounting["root_budget_id"])
    assert budget.spent == 712 and budget.reserved == 0
    response = await client.get(f"/api/cost/requests?team_id={team.id}", headers=owned_browser["headers"])
    assert response.status_code == 200
    assert any(item["call_id"] == usage.call_id for item in response.json())
    assert (await client.get(f"/api/cost/requests?team_id={uuid.uuid4()}", headers=owned_browser["headers"])).status_code == 404


def test_checkpoint_artifacts_remain_protected(tmp_path, monkeypatch):
    from core.agent import observation_cache as cache
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    cache.cache_observation("read", "evidence " * 1000, "scope")
    artifact = next(tmp_path.rglob("*.txt"))
    cache.pin_observations("scope", str(uuid.uuid4()), [{"content": artifact.name}])
    assert cache.expired_observations("scope", max_age_seconds=0) == []


def test_constraint_candidates_preserved_as_evidence_or_compaction_declined():
    from core.agent.context_condenser import ContextCondenser
    messages = [{"role": "user", "content": "Never change the public API."}]
    assert "Never change the public API." in ContextCondenser.retained_constraint_evidence(messages)
    with pytest.raises(ValueError):
        ContextCondenser.retained_constraint_evidence(messages, max_chars=3)


def test_accounting_migration_roundtrip_preserves_existing_usage(tmp_path):
    import importlib.util
    from pathlib import Path
    from sqlalchemy import create_engine, text, inspect
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    filename = Path(__file__).parents[1] / "alembic/versions/e7f9a1b3c5d7_request_accounting.py"
    spec = importlib.util.spec_from_file_location("accounting_migration", filename)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE token_usage (id VARCHAR(36) PRIMARY KEY, total_tokens INTEGER)"))
        connection.execute(text("INSERT INTO token_usage VALUES ('existing', 123)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()  # startup/create_all compatibility
            assert "accounting" in {c["name"] for c in inspect(connection).get_columns("token_usage")}
            assert connection.scalar(text("SELECT total_tokens FROM token_usage WHERE id='existing'")) == 123
            migration.downgrade()
            assert "accounting" not in {c["name"] for c in inspect(connection).get_columns("token_usage")}
            assert connection.scalar(text("SELECT total_tokens FROM token_usage WHERE id='existing'")) == 123
    engine.dispose()


@pytest.mark.asyncio
async def test_checkpoint_compare_and_swap_rejects_stale_summary(db_session):
    from core.agent.checkpoint_store import checkpoint_version, claim_checkpoint
    scope = str(uuid.uuid4())
    version = await checkpoint_version(scope)
    assert version == 0
    assert await claim_checkpoint(db_session, scope, version)
    await db_session.commit()
    assert not await claim_checkpoint(db_session, scope, version)
    await db_session.rollback()
    assert await checkpoint_version(scope) == 1


@pytest.mark.asyncio
async def test_auxiliary_completion_inherits_shared_budget_and_scope(owned_browser, db_session, monkeypatch):
    from core.agent.run_budget import create_budget, root_budget_id, request_scope
    from core.memory.models import Agent, Team, TokenUsage, RunTokenBudget
    agent = await db_session.get(Agent, uuid.UUID(owned_browser["agent_id"]))
    team = await db_session.get(Team, agent.team_id)
    run_id = str(uuid.uuid4())
    await create_budget(run_id, 10000)
    budget_token = root_budget_id.set(run_id)
    scope_token = request_scope.set({"agent_id": str(agent.id), "team_id": str(team.id),
                                     "project_id": str(team.project_id), "agent_name": agent.name})
    router = MultiModelRouter()
    await router._http_client.aclose()
    router.openai_key = "test"
    router._http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, text='data: {"choices":[{"delta":{"content":"Approved"},"finish_reason":"stop"}],"usage":{"prompt_tokens":100,"completion_tokens":2}}\n\ndata: [DONE]\n\n')))
    try:
        result = await router.generate_completion("gpt-4o-mini", "Review effects", [{"role": "user", "content": "read a file"}], purpose="safety_review")
        assert result == "Approved"
    finally:
        await router.aclose()
        request_scope.reset(scope_token)
        root_budget_id.reset(budget_token)
    usage = await db_session.scalar(select(TokenUsage).where(TokenUsage.run_id == run_id))
    assert usage.purpose == "safety_review" and usage.total_tokens == 102
    budget = await db_session.get(RunTokenBudget, run_id)
    assert budget.spent == 102 and budget.reserved == 0


@pytest.mark.asyncio
async def test_exhausted_project_blocks_before_provider_dispatch(owned_browser, db_session):
    from core.agent.run_budget import BudgetExceeded
    from core.memory.models import Agent, Team, Project
    agent = await db_session.get(Agent, uuid.UUID(owned_browser["agent_id"]))
    team = await db_session.get(Team, agent.team_id)
    project = await db_session.get(Project, team.project_id)
    project.budget_limit_usd = 0
    await db_session.commit()
    router = MultiModelRouter()
    try:
        with pytest.raises(BudgetExceeded):
            async for _ in router.generate_with_tools("gpt-4o-mini", "test", [], [], project_id=str(project.id)):
                pytest.fail("Must not dispatch")
    finally:
        await router.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["gpt-4o-mini", "claude-test", "gemini-test"])
async def test_text_only_profiles_omit_tool_configuration(model):
    router = MultiModelRouter()
    await router._http_client.aclose()
    router.openai_key = router.anthropic_key = router.gemini_key = "test"
    def respond(request):
        payload = json.loads(request.content)
        assert "tools" not in payload and "tool_choice" not in payload and "tool_config" not in payload
        if model.startswith("gemini"):
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "Hello"}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 2, "thoughtsTokenCount": 3, "cachedContentTokenCount": 50}})
        if model.startswith("claude"):
            events = [{"type": "message_start", "message": {"model": model, "id": "test", "usage": {"input_tokens": 100}}},
                      {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}},
                      {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 2}},
                      {"type": "message_stop"}]
            return httpx.Response(200, text="".join(f"data: {json.dumps(event)}\n\n" for event in events))
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
    router._http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        events = [event async for event in router.generate_with_tools(model, "Say hello", [{"role": "user", "content": "hi"}], [], allow_fallback=False)]
        assert any(event.get("delta") == "Hello" for event in events)
        if model.startswith("gemini"):
            usage = normalize_usage(next(event["usage"] for event in events if event["type"] == "usage"))
            assert usage.total_tokens == 105 and usage.reasoning_tokens == 3 and usage.cache_read_tokens == 50
    finally:
        await router.aclose()


@pytest.mark.asyncio
async def test_xml_tool_examples_never_become_executable_calls():
    router = MultiModelRouter()
    await router._http_client.aclose()
    router.openai_key = "test"
    example = '<invoke name="execute_command"><parameter name="command">dangerous example</parameter></invoke>'
    payload = {"choices": [{"delta": {"content": example}, "finish_reason": "stop"}]}
    router._http_client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, text=f"data: {json.dumps(payload)}\n\ndata: [DONE]\n\n")))
    try:
        events = [event async for event in router.generate_with_tools("gpt-4o-mini", "Explain this example", [], [], allow_fallback=False)]
        assert any(event.get("delta") == example for event in events)
        assert not any(event["type"] == "tool_use" for event in events)
    finally:
        await router.aclose()
