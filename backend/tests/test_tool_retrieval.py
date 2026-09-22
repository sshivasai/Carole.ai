from unittest.mock import AsyncMock
import uuid

import numpy as np
import pytest

from core.agent.context_compiler import count_tokens, select_schemas, tool_name
from core.agent.react_agent import ReACTAgent, resolve_active_tools
from core.tools.tool_executor import register_builtin_tools, tool_executor
from core.tools.tool_registry import ToolRegistry, ToolSpec
from core.tools.tool_retrieval import StaticCodeEmbedder, catalog_summary, discover_tools, rank_tools


@pytest.fixture
def agent(monkeypatch):
    register_builtin_tools()
    monkeypatch.setattr(ToolRegistry, "_tools", dict(ToolRegistry._tools))
    monkeypatch.setattr(ToolRegistry, "_schema_cache", {})
    monkeypatch.setattr("core.llm.config_manager.load_config", lambda: {})
    monkeypatch.setattr("core.auth.instance_owner.assert_team_instance_owner", AsyncMock())
    value = object.__new__(ReACTAgent)
    value.role = "Custom Specialist"
    value.team_id = "team"
    value.agent_id = "agent"
    value.model = "gpt-4o"
    value._host_capabilities_allowed = True
    value._dynamically_requested_tools = []
    value._cached_system_prompt = "old catalog"
    return value


@pytest.mark.parametrize("query,expected", [
    ("Take a picture of the page", "browser_screenshot"),
    ("Find out what happened in artificial intelligence this morning", "web_search"),
    ("Remind me every morning to check the dashboard", "create_scheduled_task"),
    ("Tell me what changed since my last commit", "git_diff"),
    ("preview frontend on localhost:3000", "browser_navigate"),
])
def test_real_semantic_model_handles_paraphrases(agent, query, expected):
    # Integration coverage uses the same local Model2Vec model as production.
    assert StaticCodeEmbedder.get_model() is not None
    _, names = resolve_active_tools(agent.role, query)
    assert expected in names


def test_new_plugin_is_searchable_without_routing_table_change(agent):
    plugin = ToolSpec("linguist", "Translate text from one language to another.", "languages", {}, "judge", AsyncMock())
    ToolRegistry.register(plugin)
    assert "linguist" in rank_tools("Convert this paragraph into Spanish", ToolRegistry.list_all())[:9]


def test_lexical_fallback_has_no_substring_matches(agent, monkeypatch):
    monkeypatch.setattr(StaticCodeEmbedder, "get_model", lambda: None)
    specs = [ToolSpec("runner", "Run tests in a shell", "shell", {}, "judge", AsyncMock()),
             ToolSpec("news", "Read latest news", "web", {}, "safe", AsyncMock())]
    assert rank_tools("latest news", specs) == ["news"]


def test_embedding_errors_preserve_description_discovery(agent, monkeypatch):
    def fail():
        raise RuntimeError("offline")
    monkeypatch.setattr(StaticCodeEmbedder, "get_model", fail)
    names = rank_tools("web_search", ToolRegistry.list_all())
    assert names[0] == "web_search"


def test_registry_metadata_changes_invalidate_embedding_cache(agent, monkeypatch):
    class Encoder:
        def encode(self, texts):
            return np.array([[1., 0.] if "astronom" in text or "stars" in text else [0., 1.] for text in texts])
    model = Encoder()
    monkeypatch.setattr(StaticCodeEmbedder, "get_model", lambda: model)
    spec = ToolSpec("custom", "Study astronomy", "reports", {}, "safe", AsyncMock())
    ToolRegistry.register(spec)
    assert rank_tools("stars", [ToolRegistry.get("custom")]) == ["custom"]
    ToolRegistry.register(ToolSpec("custom", "Bake bread", "reports", {}, "safe", AsyncMock()), force=True)
    assert rank_tools("stars", [ToolRegistry.get("custom")]) == []


@pytest.mark.asyncio
async def test_permission_filtering_precedes_ranking_and_cap(agent, monkeypatch):
    def ranked(query, specs):
        names = [spec.name for spec in specs]
        assert "web_search" not in names
        return names
    monkeypatch.setattr("core.tools.tool_retrieval.rank_tools", ranked)
    _, selected = await agent._select_tools("research", {"web_search": "block"})
    assert "web_search" not in selected
    assert len(selected) == 12


@pytest.mark.asyncio
async def test_catalog_refreshes_on_plugin_and_permission_changes(agent):
    from core.tools.tool_executor import get_visible_tools
    visible = get_visible_tools("team", "agent", {}, True)
    agent._tool_catalog_signature = tuple((spec.name, spec.category, spec.description) for spec in visible)
    await agent._select_tools("", {})
    assert agent._cached_system_prompt == "old catalog"
    ToolRegistry.register(ToolSpec("fresh_tool", "Fresh plugin", "new_family", {}, "safe", AsyncMock()))
    await agent._select_tools("", {})
    assert agent._cached_system_prompt is None
    agent._cached_system_prompt = "old catalog"
    await agent._select_tools("", {"web_search": "block"})
    assert agent._cached_system_prompt is None


@pytest.mark.parametrize("model", ["gpt-4o", "gemini-test", "claude-test"])
def test_schema_budget_preserves_relevance_across_providers(agent, monkeypatch, model):
    monkeypatch.setattr("core.agent.react_agent.llm_router.anthropic_key", "test")
    agent.model = model
    for name in ["aaa_irrelevant", "zzz_relevant"]:
        ToolRegistry.register(ToolSpec(name, "Description", "reports", {}, "safe", AsyncMock()))
    ordered = ["fetch_tool_schemas", "zzz_relevant", "aaa_irrelevant"]
    schemas = agent._build_tools_schema({"reports", "coordination"}, ordered, {})
    declarations = [decl for item in schemas for decl in item.get("functionDeclarations", [item])]
    budget = count_tokens(declarations[:2], model)
    selected = select_schemas(schemas, budget, model)
    names = {tool_name(decl) for item in selected for decl in item.get("functionDeclarations", [item])}
    assert names == {"fetch_tool_schemas", "zzz_relevant"}


@pytest.mark.asyncio
async def test_query_discovery_loads_schema_in_next_request(agent):
    args = {"query": "Take a picture of the page"}
    result = await tool_executor.execute("fetch_tool_schemas", args,
        agent_id="agent", agent_name="Nova", team_id="team", permissions={})
    assert "browser_screenshot" in result
    agent._activate_discovered_tools(args, {})
    categories, names = await agent._select_tools("unrelated original task", {})
    schemas = agent._build_tools_schema(categories, names, {})
    selected = select_schemas(schemas, 1, agent.model, agent._dynamically_requested_tools)
    assert "browser_screenshot" in {tool_name(schema) for schema in selected}


def test_multiple_discoveries_keep_recent_tools_and_failed_search_preserves_them(agent):
    agent._activate_discovered_tools({"tool_names": ["web_search"]}, {})
    agent._activate_discovered_tools({"tool_names": ["browser_navigate"]}, {})
    assert agent._dynamically_requested_tools[:2] == ["browser_navigate", "web_search"]
    agent._activate_discovered_tools({"tool_names": ["nonexistent"]}, {})
    assert agent._dynamically_requested_tools[:2] == ["browser_navigate", "web_search"]


def test_catalog_does_not_hide_late_families(agent):
    specs = [ToolSpec(f"tool_{i}", "Long description " * 30, "aaa", {}, "safe", AsyncMock()) for i in range(30)]
    specs.append(ToolSpec("late_tool", "Late plugin", "zzz", {}, "safe", AsyncMock()))
    catalog = catalog_summary(specs, max_chars=250)
    assert "aaa, zzz" in catalog
    assert "query=" in catalog


def test_uuid_scoped_tools_are_consistent_across_provider_schemas(agent):
    team_id, agent_id = uuid.uuid4(), uuid.uuid4()
    ToolRegistry.register(ToolSpec("scoped", "Scoped plugin", "reports", {}, "safe", AsyncMock(), team_id=team_id, agent_id=agent_id))
    for convert in [ToolRegistry.to_openai_tools, ToolRegistry.to_anthropic_tools, ToolRegistry.to_gemini_tools]:
        schemas = convert(team_id=str(team_id), agent_id=str(agent_id), include_names={"scoped"})
        assert schemas
        assert not convert(team_id="other", agent_id=str(agent_id), include_names={"scoped"})


@pytest.mark.parametrize("optimization,expected", [({}, 1), ({"tool_budgeting": False}, 2), ({"shadow_mode": True}, 2)])
def test_fallback_and_primary_use_the_same_budget_policy(agent, optimization, expected):
    from core.agent.context_compiler import ContextPolicy
    agent._context_policy = ContextPolicy("work", 24000, 1, 8192)
    names = ["fetch_tool_schemas", "web_search"]
    for model in ["gpt-4o", "gemini-test"]:
        agent._active_model = model
        schemas = agent._prepare_tools({"coordination", "web"}, names, {}, model, optimization)
        assert len([decl for item in schemas for decl in item.get("functionDeclarations", [item])]) == expected


def test_chat_policy_has_no_tools_even_with_discovered_names(agent):
    from core.agent.context_compiler import CHAT
    agent._context_policy = CHAT
    agent._dynamically_requested_tools = ["web_search"]
    assert agent._prepare_tools({"web"}, ["web_search"], {}, agent.model, {}) == []
