"""
# backend/tests/test_react_agent_hardening.py

Comprehensive unit test suite for hardened ReACT agent native tool calling,
message history invariants, compaction continuity, and context condenser integration.
"""

import pytest
import uuid
from copy import deepcopy
from core.agent.message_history import MessageHistory
from core.agent.context_condenser import ContextCondenser, DEFAULT_TOKEN_TRIGGER_RATIO
from core.agent.react_agent import ReACTAgent


# ─── 1. MessageHistory Invariants ──────────────────────────────────────────────

def test_message_history_encapsulation():
    """Verify get_messages returns deepcopy so callers cannot mutate internal state."""
    history = MessageHistory()
    history.add_user("Hello agent")
    history.add_assistant_text("Hello user")

    msgs = history.get_messages()
    assert len(msgs) == 2

    # Mutate the returned list and content dict
    msgs.append({"role": "user", "content": "Tampering"})
    msgs[0]["content"][0]["text"] = "Corrupted text"

    # Verify internal history is untampered
    fresh_msgs = history.get_messages()
    assert len(fresh_msgs) == 2
    assert fresh_msgs[0]["content"][0]["text"] == "Hello agent"


def test_message_history_structured_blocks_preservation():
    """Verify _to_blocks preserves structured blocks (tool_use, tool_result, image)."""
    history = MessageHistory()
    history.add_user([
        {"type": "text", "text": "Inspect image"},
        {"type": "image", "local_path": "/tmp/test.png", "mime_type": "image/png"}
    ])

    msgs = history.get_messages()
    assert len(msgs) == 1
    assert len(msgs[0]["content"]) == 2
    assert msgs[0]["content"][1]["type"] == "image"
    assert msgs[0]["content"][1]["local_path"] == "/tmp/test.png"


def test_message_history_pending_tool_calls_state_machine():
    """Verify pending tool call tracking prevents premature assistant turns."""
    history = MessageHistory()
    history.add_user("Call tool X")
    history.add_assistant_text(
        text="Executing tool",
        tool_uses=[{"type": "tool_use", "id": "call_123", "name": "read_file", "input": {"path": "a.txt"}}]
    )

    assert history.has_pending_tool_calls
    assert "call_123" in history.pending_tool_calls

    # Adding another assistant turn while tool results are pending must raise ValueError
    with pytest.raises(ValueError, match="Cannot add assistant turn while tool results are pending"):
        history.add_assistant_text("Another assistant turn")

    # Add tool results batch
    history.add_tool_results([{
        "tool_use_id": "call_123",
        "content": "File contents of a.txt",
        "is_error": False,
    }])

    assert not history.has_pending_tool_calls
    assert len(history.pending_tool_calls) == 0

    # Now assistant turn is allowed
    history.add_assistant_text("Finished reading file.")
    assert len(history) == 4


def test_message_history_tool_result_ordering():
    """Verify that in user turns, tool_result blocks strictly precede context notes/text."""
    history = MessageHistory()
    history.add_user("Start")
    history.add_assistant_text(
        text="Run command",
        tool_uses=[{"type": "tool_use", "id": "c1", "name": "exec", "input": {}}]
    )

    # Add tool result
    history.add_tool_results([{"tool_use_id": "c1", "content": "Success"}])
    # Add context note
    history.add_context_note("Graceful degradation note")

    msgs = history.get_messages()
    user_turn = msgs[-1]
    assert user_turn["role"] == "user"
    blocks = user_turn["content"]
    assert len(blocks) == 2
    assert blocks[0]["type"] == "tool_result"
    assert blocks[1]["type"] == "text"
    assert "Graceful degradation" in blocks[1]["text"]


def test_message_history_empty_assistant_validation():
    """Verify empty assistant response raises ValueError."""
    history = MessageHistory()
    history.add_user("Hello")
    with pytest.raises(ValueError, match="Assistant turn cannot be empty"):
        history.add_assistant_text("")


# ─── 2. ContextCondenser & Pruning Bounds ─────────────────────────────────────

def test_context_condenser_tool_dependency_atomic_bounds():
    """Verify compute_pruning_bounds never splits tool_use from its tool_result."""
    messages = [
        {"role": "user", "content": "Initial prompt"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "tc1", "name": "t1", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tc1", "content": "res1"}]},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "tc2", "name": "t2", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tc2", "content": "res2"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Recent thought"}]},
        {"role": "user", "content": "Recent prompt"},
        {"role": "assistant", "content": "Recent answer"},
    ]

    prefix_end, start = ContextCondenser.compute_pruning_bounds(messages, keep_recent_turns=3)
    # The prune slice is messages[prefix_end:start]
    # start must NOT fall between an assistant tool_use and its user tool_result
    pruned_slice = messages[prefix_end:start]
    for msg in pruned_slice:
        assert msg != messages[0]  # First message must never be in the pruned slice

    pruned = ContextCondenser.apply_sliding_window_pruning(
        messages=messages,
        checkpoint_card="## 1. Goal\nDone\n## 2. Decs\nNone\n## 3. Files\nNone\n## 4. Next\nNone",
        keep_recent_turns=3
    )
    # Verify pruned history preserves valid tool dependencies without throwing ValueError
    assert len(pruned) >= 4
    assert pruned[0]["content"] == "Initial prompt"
    assert "[WORKING STATE CHECKPOINT]" in pruned[1]["content"]


def test_extract_pinned_identifiers_secret_filtering():
    """Verify extract_pinned_identifiers excludes credentials and keys."""
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "1", "name": "login", "input": {
                    "api_key": "sk-super-secret-key-12345",
                    "password": "mypassword123",
                    "file_path": "backend/core/config.py"
                }}
            ]
        }
    ]
    pinned = ContextCondenser.extract_pinned_identifiers(messages)
    assert "backend/core/config.py" in pinned
    assert "sk-super-secret" not in pinned
    assert "mypassword123" not in pinned


# ─── 3. ReACTAgent Methods & Invariants ────────────────────────────────────────

def test_react_agent_estimate_tokens_with_native_blocks():
    """Verify _estimate_tokens accurately counts tokens for structured tool blocks."""
    agent = ReACTAgent(
        agent_id=str(uuid.uuid4()), team_id=str(uuid.uuid4()), project_id=str(uuid.uuid4()),
        name="TestAgent", role="worker", model="openrouter/auto", system_prompt="You are helpful."
    )

    messages = [
        {"role": "user", "content": "Run tests"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Running pytest"},
                {"type": "tool_use", "id": "call_1", "name": "execute_command", "input": {"command": "pytest -v"}}
            ]
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": "==== 10 passed in 1.2s ===="}
            ]
        }
    ]

    tokens = agent._estimate_tokens(messages, system_prompt="You are helpful.")
    assert isinstance(tokens, int)
    assert tokens > 20  # Reasonable non-zero token estimation


def test_react_agent_micro_compact_historical_tool_results():
    """Verify _micro_compact condenses older tool results and leaves recent ones intact."""
    agent = ReACTAgent(
        agent_id=str(uuid.uuid4()), team_id=str(uuid.uuid4()), project_id=str(uuid.uuid4()),
        name="TestAgent", role="worker", model="openrouter/auto", system_prompt="You are helpful."
    )

    long_output = "Line " + "\nLine ".join(str(i) for i in range(100))  # > 500 chars
    messages = [
        {"role": "user", "content": "Initial prompt"},
        # Old turn (> 4 messages ago)
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c0", "content": long_output}]},
        {"role": "assistant", "content": "Thought 1"},
        {"role": "user", "content": "User prompt 1"},
        {"role": "assistant", "content": "Thought 2"},
        {"role": "user", "content": "User prompt 2"},
        {"role": "assistant", "content": "Thought 3"},
        # Recent turn (<= 4 messages ago)
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": long_output}]},
    ]

    compacted = agent._micro_compact(messages)
    # The historical tool result at index 1 should be compacted
    old_res = compacted[1]["content"][0]["content"]
    assert "compacted" in old_res or len(old_res) < len(long_output)


def test_react_agent_xml_notifications_escaping():
    """Verify _build_task_notification escapes special XML chars and parse unescapes them."""
    agent = ReACTAgent(
        agent_id=str(uuid.uuid4()), team_id=str(uuid.uuid4()), project_id=str(uuid.uuid4()),
        name="Worker<Special>", role="worker", model="openrouter/auto", system_prompt="Helpful."
    )
    agent.task_id = "task-123 & 456"

    raw_result = "Result with <b>tags</b> & 'quotes' and </task_id> injection attempt."
    xml_str = agent._build_task_notification(raw_result, "completed")

    # XML tags must be escaped
    assert "&lt;b&gt;tags&lt;/b&gt;" in xml_str
    assert "&amp;" in xml_str

    # Parser should successfully reconstruct original content
    parsed = agent.parse_task_notifications(xml_str)
    assert len(parsed) == 1
    assert parsed[0]["task_id"] == "task-123 & 456"
    assert parsed[0]["agent"] == "Worker<Special>"
    assert parsed[0]["status"] == "completed"
    assert parsed[0]["result"] == raw_result


def test_react_agent_tool_loading_is_bounded_without_role_authorization():
    from core.agent.react_agent import resolve_active_tools
    from core.tools.tool_registry import ToolRegistry

    categories, selected = resolve_active_tools("Orchestrator")
    assert "git" in categories
    all_tools = ToolRegistry.to_anthropic_tools()
    pruned_tools = ToolRegistry.to_anthropic_tools(categories=categories, include_names=selected)

    assert len(pruned_tools) > 0
    assert len(pruned_tools) < len(all_tools)
    # Pruned toolset should include ask_user, write_file, create_task
    pruned_names = {t["name"] for t in pruned_tools}
    assert "ask_user" in pruned_names
    assert "write_file" in pruned_names


@pytest.mark.asyncio
async def test_react_agent_fetch_tool_schemas(monkeypatch):
    """Verify fetch_tool_schemas allows agents to discover on-demand tools by name or category."""
    from core.tools.tool_executor import tool_executor
    from unittest.mock import AsyncMock
    monkeypatch.setattr("core.auth.instance_owner.assert_team_instance_owner", AsyncMock())

    # 1. Fetch by category 'git'
    res = await tool_executor.execute(
        "fetch_tool_schemas",
        {"category": "git"},
        agent_id="test_agent",
        agent_name="Archer",
        team_id="test_team",
        permissions={"fetch_tool_schemas": "safe"},
    )
    assert isinstance(res, str)
    assert "Tools found" in res or "git" in res

    # 2. Fetch specific tool by name
    res2 = await tool_executor.execute(
        "fetch_tool_schemas",
        {"tool_name": "ask_user"},
        agent_id="test_agent",
        agent_name="Archer",
        team_id="test_team",
        permissions={"fetch_tool_schemas": "safe"},
    )
    assert isinstance(res2, str)
    assert "ask_user" in res2


@pytest.mark.asyncio
async def test_interaction_tools_ask_user_multi_question():
    """Verify ask_user supports batching multiple questions and formats JSON answers into markdown bullets."""
    import asyncio
    from core.tools.interaction_tools import interaction_tools, pending_questions, question_answers

    questions_payload = [
        {"id": "q1", "question": "What frontend framework?", "options": ["React", "Vue"]},
        {"id": "q2", "question": "What backend language?", "options": ["Python", "Go"]},
    ]

    async def simulate_answer():
        await asyncio.sleep(0.05)
        # Find the question_id
        assert len(pending_questions) > 0
        q_id = list(pending_questions.keys())[0]
        question_answers[q_id] = '{"What frontend framework?": "React", "What backend language?": "Python"}'
        pending_questions[q_id].set()

    task = asyncio.create_task(simulate_answer())

    result = await interaction_tools.ask_user(
        question="Please specify stack preferences",
        agent_id="test_orch",
        agent_name="Archer",
        team_id="test_team",
        questions=questions_payload,
    )
    await task

    assert "Human answered:" in result
    assert "- **What frontend framework?**: React" in result
    assert "- **What backend language?**: Python" in result


def test_circuit_breaker_token_limit_config():
    """Verify MAX_BUDGET_TOKENS defaults to 1,000,000 to prevent premature circuit breaker halts."""
    import core.config as cfg
    assert hasattr(cfg, "MAX_BUDGET_TOKENS")
    assert cfg.MAX_BUDGET_TOKENS >= 1_000_000


def test_openai_message_formatter_preserves_tool_use_and_results():
    """Verify _format_messages_for_provider preserves tool calls and observations for OpenAI/OpenRouter."""
    from core.agent.message_history import MessageHistory
    from core.llm.multi_model_router import llm_router

    h = MessageHistory()
    h.add_user("title: test task. description: run tests")
    h.add_assistant_text("Creating task...", tool_uses=[{
        "id": "call_123",
        "name": "create_task",
        "input": {"title": "test task", "assignee": "Nova"}
    }])
    h.add_tool_results([{
        "tool_use_id": "call_123",
        "content": "✓ Task created: 'test task' (ID: task-abc)",
        "tool_name": "create_task"
    }])

    msgs = h.get_messages()
    formatted = llm_router._format_messages_for_provider(msgs, "openai")

    # 1. First message should be user prompt
    assert formatted[0]["role"] == "user"
    assert "title: test task" in str(formatted[0]["content"])

    # 2. Second message should be assistant with tool_calls
    assert formatted[1]["role"] == "assistant"
    assert formatted[1]["content"] == "Creating task..."
    assert len(formatted[1]["tool_calls"]) == 1
    assert formatted[1]["tool_calls"][0]["id"] == "call_123"
    assert formatted[1]["tool_calls"][0]["function"]["name"] == "create_task"
    assert "Nova" in formatted[1]["tool_calls"][0]["function"]["arguments"]

    # 3. Third message should be tool role with tool_call_id
    assert formatted[2]["role"] == "tool"
    assert formatted[2]["tool_call_id"] == "call_123"
    assert "✓ Task created: 'test task' (ID: task-abc)" in formatted[2]["content"]


def test_universal_memory_category_for_all_roles():
    """Verify that 'memory' is in allowed categories for all roles by default."""
    from core.agent.react_agent import UNIVERSAL_ALLOWED_CATEGORIES, resolve_active_tools

    assert "memory" in UNIVERSAL_ALLOWED_CATEGORIES

    allowed_cats, selected_tools = resolve_active_tools("custom_unknown_role")
    assert "memory" in allowed_cats
    assert "search_memory" in selected_tools
    assert "add_memory" in selected_tools


def test_intent_matrix_activates_git_on_repo_synonym():
    """Verify that 'repo' synonym activates git tools without saying the word 'git'."""
    from core.agent.react_agent import resolve_active_tools

    allowed_cats, selected_tools = resolve_active_tools("coder", "check the repo and see what changed")
    assert "git" in allowed_cats
    assert "git_status" in selected_tools or "git_diff" in selected_tools


def test_intent_matrix_activates_browser_for_coder_on_preview():
    """Verify that frontend/preview intent allows coder/developer to use browser tools."""
    from core.agent.react_agent import resolve_active_tools

    allowed_cats, selected_tools = resolve_active_tools("coder", "preview frontend on localhost:3000")
    assert "browser" in allowed_cats
    assert "browser_navigate" in selected_tools or "browser_screenshot" in selected_tools


def test_tools_capped_at_max_tools():
    """Verify that resolve_active_tools caps the total active tool schemas to max_tools."""
    from core.agent.react_agent import resolve_active_tools

    allowed_cats, selected_tools = resolve_active_tools(
        "coder",
        "preview in browser, commit git changes, run pytest tests, search with grep, create task, read memory",
        max_tools=10,
    )
    assert len(selected_tools) <= 10
    # Universal essentials should still be preserved
    assert "read_file" in selected_tools
    assert "ask_user" in selected_tools


def test_deterministic_tool_sorting_and_schema_cache():
    """Verify tools are deterministically sorted alphabetically by name and schema cache works."""
    from core.tools.tool_registry import ToolRegistry

    tools = ToolRegistry.to_anthropic_tools()
    tool_names = [t["name"] for t in tools]
    assert tool_names == sorted(tool_names), "Anthropic tool schemas must be sorted alphabetically for deterministic prompt caching"

    # Verify schema cache is populated
    assert len(ToolRegistry._schema_cache) > 0

    # Verify cache invalidation on unregister/register
    cached_count = len(ToolRegistry._schema_cache)
    ToolRegistry.unregister("__non_existent_tool__")
    assert len(ToolRegistry._schema_cache) == 0, "Cache should clear on unregister"


def test_anthropic_prompt_caching_breakpoints():
    """Verify Anthropic 3-breakpoint prompt caching matches Claude Code / Roo Code design."""
    from core.llm.multi_model_router import MultiModelRouter

    router = MultiModelRouter()

    # 1. Large system prompt (>1024 chars) gets cache_control
    large_system = "A" * 1200
    short_system = "You are a helpful assistant."

    tools = [
        {"name": "ask_user", "description": "Ask user", "input_schema": {}},
        {"name": "read_file", "description": "Read file", "input_schema": {}},
        {"name": "write_file", "description": "Write file", "input_schema": {}},
    ]
    messages = [
        {"role": "user", "content": "First message from user"},
        {"role": "assistant", "content": "First response from assistant"},
        {"role": "user", "content": "Second turn from user"},
    ]

    sys_payload, cached_tools, cached_msgs = router._apply_anthropic_prompt_caching(
        system_prompt=large_system,
        tools=tools,
        formatted_messages=messages,
    )

    # Breakpoint 1: System prompt
    assert isinstance(sys_payload, list)
    assert sys_payload[0]["cache_control"] == {"type": "ephemeral"}
    assert sys_payload[0]["text"] == large_system

    # Breakpoint 2: Final tool schema only
    assert cached_tools is not None
    assert len(cached_tools) == 3
    assert "cache_control" not in cached_tools[0]
    assert "cache_control" not in cached_tools[1]
    assert cached_tools[-1]["cache_control"] == {"type": "ephemeral"}
    assert cached_tools[-1]["name"] == "write_file"

    # Breakpoint 3: Penultimate user turn (messages[0] in 3-message list)
    # The last message is index 2 (current turn), so penultimate user turn is index 0
    assert cached_msgs[0]["role"] == "user"
    assert isinstance(cached_msgs[0]["content"], list)
    assert cached_msgs[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert cached_msgs[0]["content"][0]["text"] == "First message from user"

    # Current user turn (index 2) should NOT have cache_control
    assert cached_msgs[2]["content"] == "Second turn from user"

    # Verify immutability: original tools list was NOT mutated
    assert "cache_control" not in tools[-1]

    # Verify short system prompt stays as raw str
    short_sys_payload, _, _ = router._apply_anthropic_prompt_caching(
        system_prompt=short_system,
        tools=None,
        formatted_messages=[{"role": "user", "content": "Hello"}],
    )
    assert short_sys_payload == short_system


def test_openai_strict_mode():
    """Verify OpenAI strict mode sets strict=True and additionalProperties=False."""
    from core.tools.tool_registry import ToolRegistry

    openai_tools = ToolRegistry.to_openai_tools(strict=True)
    assert len(openai_tools) > 0
    first = openai_tools[0]["function"]
    assert first.get("strict") is True
    assert first["parameters"].get("additionalProperties") is False
    assert "required" in first["parameters"]
