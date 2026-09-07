import pytest
from core.agent.react_agent import ReACTAgent


def test_detect_oscillating_loop_period_2():
    # Sequence of A -> B -> A -> B (period 2)
    sigs = [
        "read_file:abc123",
        "grep_search:def456",
        "read_file:abc123",
        "grep_search:def456"
    ]
    detected = ReACTAgent._detect_oscillating_loop(sigs)
    assert detected is not None
    assert "Oscillating tool cycle (read_file -> grep_search)" in detected


def test_detect_oscillating_loop_period_3():
    # Sequence of A -> B -> C -> A -> B -> C (period 3)
    sigs = [
        "list_directory:111",
        "read_file:222",
        "grep_search:333",
        "list_directory:111",
        "read_file:222",
        "grep_search:333"
    ]
    detected = ReACTAgent._detect_oscillating_loop(sigs)
    assert detected is not None
    assert "list_directory -> read_file -> grep_search" in detected


def test_detect_oscillating_loop_no_cycle():
    # Benign progressive workflow: A -> B -> C -> D -> E
    sigs = [
        "list_directory:111",
        "read_file:222",
        "edit_file:333",
        "execute_command:444",
        "git_commit:555"
    ]
    detected = ReACTAgent._detect_oscillating_loop(sigs)
    assert detected is None


def test_detect_oscillating_loop_short():
    sigs = ["read_file:111", "grep_search:222"]
    assert ReACTAgent._detect_oscillating_loop(sigs) is None
