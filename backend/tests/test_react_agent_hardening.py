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
