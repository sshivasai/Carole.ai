from unittest.mock import AsyncMock

import pytest

from core.agent.context_compiler import select_schemas
from core.agent.react_agent import ReACTAgent, resolve_active_tools
from core.tools.tool_executor import get_visible_tools, tool_executor
from core.tools.tool_registry import ToolRegistry, ToolSpec


@pytest.fixture
def discovery_agent(monkeypatch):
    monkeypatch.setattr("core.llm.config_manager.load_config", lambda: {})
    monkeypatch.setattr("core.auth.instance_owner.assert_team_instance_owner", AsyncMock())
    monkeypatch.setattr(ToolRegistry, "_tools", dict(ToolRegistry._tools))
    monkeypatch.setattr(ToolRegistry, "_schema_cache", {})
    agent = object.__new__(ReACTAgent)
    agent.role = "Software Engineer"
    agent.team_id = "test-team"
    agent.agent_id = "test-agent"
    agent.model = "gpt-4o"
    agent._host_capabilities_allowed = True
    agent._dynamically_requested_tools = []
    return agent


@pytest.mark.parametrize("role", ["Software Engineer", "Coder", "Reviewer", "Custom Specialist"])
def test_browser_and_web_request_works_for_any_role(discovery_agent, role):
    categories, selected = resolve_active_tools(
        role, "hey @Nova, can you open the browser and search for latest news in ai?")
    schemas = discovery_agent._build_tools_schema(categories, selected, {})
    names = {tool["function"]["name"] for tool in schemas}
    assert {"fetch_tool_schemas", "browser_navigate", "web_search"} <= names
    assert len(names) <= 12


def test_discovery_tool_is_available_without_role_match(discovery_agent):
    categories, selected = resolve_active_tools("Unrecognized Title", "hello")
    schemas = discovery_agent._build_tools_schema(categories, selected, {})
    assert "fetch_tool_schemas" in {tool["function"]["name"] for tool in schemas}


@pytest.mark.parametrize("gate", ["judge", "human"])
def test_non_role_tool_survives_discovery_and_schema_budget(discovery_agent, gate):
    ToolRegistry.register(ToolSpec("external_report", "Generate a report", "reports", {}, gate, AsyncMock()))
    result = discovery_agent._activate_discovered_tools({"tool_names": ["external_report"]}, {})
    assert "Schemas loaded for the next model call: external_report." in result
    categories, selected = resolve_active_tools(
        discovery_agent.role, dynamically_requested_tools=discovery_agent._dynamically_requested_tools)
    schemas = discovery_agent._build_tools_schema(categories, selected, {})
    budgeted = select_schemas(schemas, 1, "gpt-4o", discovery_agent._dynamically_requested_tools)
    assert "external_report" in {tool["function"]["name"] for tool in budgeted}


def test_new_discovery_takes_priority_over_full_previous_batch(discovery_agent):
    for index in range(15):
        ToolRegistry.register(ToolSpec(f"report_{index:02}", "Report", "reports", {}, "judge", AsyncMock()))
    result = discovery_agent._activate_discovered_tools({"family": "reports"}, {})
    assert "Other permitted tools" in result
    assert len(discovery_agent._dynamically_requested_tools) == 9
    assert "report_14" not in discovery_agent._dynamically_requested_tools
    result = discovery_agent._activate_discovered_tools({"tool_names": ["report_14"]}, {})
    assert "Schemas loaded for the next model call: report_14." in result
    assert discovery_agent._dynamically_requested_tools[0] == "report_14"
    assert len(discovery_agent._dynamically_requested_tools) == 9


def test_visibility_preserves_permission_scope_and_host_boundaries(discovery_agent):
    for name, kwargs in [
        ("other_team_report", {"team_id": "other-team"}),
        ("other_agent_report", {"agent_id": "other-agent"}),
        ("blocked_report", {}),
        ("denied_report", {}),
        ("host_report", {"requires_instance_owner": True}),
        ("allowed_report", {}),
    ]:
        ToolRegistry.register(ToolSpec(name, "Report", "reports", {}, "judge", AsyncMock(), **kwargs))
    permissions = {"overrides": {"blocked_report": "block"}, "always_deny": ["denied_report"]}
    discovery_agent._host_capabilities_allowed = False
    visible = get_visible_tools("test-team", "test-agent", permissions, False)
    assert {spec.name for spec in visible if spec.category == "reports"} == {"allowed_report"}
    result = discovery_agent._activate_discovered_tools({"family": "reports"}, permissions)
    assert discovery_agent._dynamically_requested_tools == ["allowed_report"]
    assert "other_team_report" not in result
    categories, selected = resolve_active_tools("Software Engineer", dynamically_requested_tools={
        "blocked_report", "denied_report", "other_team_report", "other_agent_report", "host_report", "allowed_report"})
    schemas = discovery_agent._build_tools_schema(categories, selected, permissions)
    report_names = {t["function"]["name"] for t in schemas if t["function"]["name"].endswith("_report")}
    assert report_names == {"allowed_report"}


@pytest.mark.asyncio
async def test_discovery_cannot_forge_policy_or_leak_scoped_tools(discovery_agent):
    ToolRegistry.register(ToolSpec("private_report", "Private metadata", "reports", {}, "safe", AsyncMock(), team_id="other-team"))
    result = await tool_executor.execute(
        "fetch_tool_schemas",
        {"tool_names": ["private_report", "web_search"], "_tool_permissions": {"web_search": "safe"}},
        agent_id="test-agent", agent_name="Nova", team_id="test-team",
        permissions={"web_search": "block"},
    )
    assert "No matching permitted tools" in result
    assert "Private metadata" not in result
    assert "private_report" not in result
    assert "**web_search**" not in result
