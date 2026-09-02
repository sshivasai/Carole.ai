"""
# backend/tests/test_context_condenser.py

Tests for Phase 2: ContextCondenser, Working State Checkpoints, sliding window pruning, and orphan tag sanitization.
"""

import pytest
from core.agent.context_condenser import ContextCondenser, DEFAULT_TOKEN_TRIGGER_RATIO


def test_token_pressure_detection():
    # 70k tokens in 100k window (70% < 75%)
    assert not ContextCondenser.is_under_context_pressure(70_000, 100_000, DEFAULT_TOKEN_TRIGGER_RATIO)

    # 75k tokens in 100k window (75% == 75%)
    assert ContextCondenser.is_under_context_pressure(75_000, 100_000, DEFAULT_TOKEN_TRIGGER_RATIO)

    # 85k tokens in 100k window (85% > 75%)
    assert ContextCondenser.is_under_context_pressure(85_000, 100_000, DEFAULT_TOKEN_TRIGGER_RATIO)


def test_orphan_tag_sanitizer():
    # Unclosed ACTION tag
    corrupted_1 = "I will edit the file: [ACTION]edit_file({'path': 'main.py'})"
    sanitized_1 = ContextCondenser.sanitize_orphan_tags(corrupted_1)
    assert sanitized_1.endswith("[/ACTION]")
    assert sanitized_1.count("[ACTION]") == sanitized_1.count("[/ACTION]")

    # Unclosed OBSERVATION tag
    corrupted_2 = "[OBSERVATION] Output: build passed successfully"
    sanitized_2 = ContextCondenser.sanitize_orphan_tags(corrupted_2)
    assert sanitized_2.endswith("[/OBSERVATION]")
    assert sanitized_2.count("[OBSERVATION]") == sanitized_2.count("[/OBSERVATION]")

    # Dangling closing tag without open
    corrupted_3 = "All finished.[/ACTION] Next step ready."
    sanitized_3 = ContextCondenser.sanitize_orphan_tags(corrupted_3)
    assert "[/ACTION]" not in sanitized_3


def test_extract_pinned_identifiers():
    messages = [
        {"role": "user", "content": "Please inspect backend/core/agent/react_agent.py and frontend/src/App.tsx"},
        {"role": "assistant", "content": "[ACTION]read_file({'path': 'backend/core/memory/models.py'})[/ACTION]"},
        {"role": "user", "content": "[OBSERVATION] File read complete [/OBSERVATION]"},
    ]
    pinned = ContextCondenser.extract_pinned_identifiers(messages)
    assert "backend/core/agent/react_agent.py" in pinned
    assert "frontend/src/App.tsx" in pinned
    assert "backend/core/memory/models.py" in pinned
    assert "[PINNED CONTEXT: ACTIVE WORKSPACE IDENTIFIERS]" in pinned


def test_sliding_window_pruning():
    messages = [
        {"role": "user", "content": "Initial prompt: build feature X"},
        {"role": "assistant", "content": "Turn 1 thought and action"},
        {"role": "user", "content": "Turn 1 obs"},
        {"role": "assistant", "content": "Turn 2 thought and action"},
        {"role": "user", "content": "Turn 2 obs"},
        {"role": "assistant", "content": "Turn 3 thought and action"},
        {"role": "user", "content": "Turn 3 obs"},
        {"role": "assistant", "content": "Turn 4 thought and action"},
        {"role": "user", "content": "Turn 4 obs"},
    ]

    checkpoint_card = (
        "## 1. Active Goal & User Constraints\n- Build feature X\n"
        "## 2. Architectural & Implementation Decisions Made\n- Used pattern Y\n"
        "## 3. List of Modified & Created Files\n- main.py\n"
        "## 4. Blockers & Next Immediate Steps\n- None"
    )

    pruned = ContextCondenser.apply_sliding_window_pruning(messages, checkpoint_card, keep_recent_turns=4)

    # Must preserve: messages[0] + [WORKING STATE CHECKPOINT] + last 4 messages
    assert len(pruned) == 1 + 1 + 4
    assert pruned[0]["content"] == "Initial prompt: build feature X"
    assert "[WORKING STATE CHECKPOINT]" in pruned[1]["content"]
    assert "## 1. Active Goal & User Constraints" in pruned[1]["content"]
    assert pruned[-4:] == messages[-4:]
