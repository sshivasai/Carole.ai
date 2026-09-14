# tests/core/agent/test_intent_engine.py

import pytest

from core.agent.intent_engine import (
    CapabilityContext,
    IntentEngine,
    IntentKind,
    IssueKind,
)

@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Open the browser", True),
        ("Please search for Python 3.14 changes", True),
        ("Can you please create a file?", True),
        ("Help me fix this test", True),
        ("Look up the latest release", True),
        ("How does authentication work?", False),
        ("How to build an API", False),
        ("What tools do you have?", False),
        ("Do you have filesystem access?", False),
        ("Tell me how to deploy this", False),
        ("How does auth work? Find the middleware.", True),
        ("@Archer please inspect the logs", True),
    ],
)
def test_is_action_request(prompt: str, expected: bool) -> None:
    assert IntentEngine.is_action_request(prompt) is expected

def test_detailed_action_result() -> None:
    result = IntentEngine.analyze("Please update the configuration")

    assert result.kind is IntentKind.ACTION
    assert result.requires_action is True
    assert result.confidence >= 0.9

def test_unexecuted_promise() -> None:
    issue = IntentEngine.detect_response_issue(
        "I'll search the repository now.",
        has_tool_call=False,
    )

    assert issue is not None
    assert issue.kind is IssueKind.UNEXECUTED_PROMISE

def test_promise_allowed_when_tool_was_called() -> None:
    issue = IntentEngine.detect_response_issue(
        "I'll search the repository now.",
        has_tool_call=True,
    )

    assert issue is None

def test_harmless_let_me_know() -> None:
    issue = IntentEngine.detect_response_issue(
        "Let me know if you want another example.",
        has_tool_call=False,
    )

    assert issue is None

def test_refusal_not_false_without_runtime_capability() -> None:
    result = IntentEngine.detect_false_refusal(
        "I can't browse the internet.",
        capabilities=CapabilityContext(browser_available=False),
    )

    assert result is None

def test_browser_capability_mismatch() -> None:
    result = IntentEngine.detect_false_refusal(
        "I can't access the web.",
        capabilities=CapabilityContext(browser_available=True),
    )

    assert result is not None
    assert "capability_mismatch" in result
