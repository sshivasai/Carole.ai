"""
# backend/tests/test_action_gating.py

Tests for Phase 1: IntentEngine, Turn-1 action gating, false refusal interception, and unexecuted promise handling.
"""

import pytest
from core.agent.intent_engine import IntentEngine


def test_intent_engine_action_requests():
    # Direct imperative commands
    assert IntentEngine.is_action_request("open google.com and search for AI news")
    assert IntentEngine.is_action_request("navigate to https://github.com")
    assert IntentEngine.is_action_request("browse the repo and find the main file")
    assert IntentEngine.is_action_request("create a new file named index.html")
    assert IntentEngine.is_action_request("fix the broken test in test_auth.py")
    assert IntentEngine.is_action_request("write a python script to parse logs")
    assert IntentEngine.is_action_request("run pytest")
    assert IntentEngine.is_action_request("execute npm run build")
    assert IntentEngine.is_action_request("edit the configuration to enable debug mode")
    assert IntentEngine.is_action_request("hire a QA subagent to write tests")

    # Subject + Modal + Verb commands
    assert IntentEngine.is_action_request("I need you to open google.com")
    assert IntentEngine.is_action_request("Can you please search for the latest tech news?")
    assert IntentEngine.is_action_request("Please create a test suite")
    assert IntentEngine.is_action_request("I want you to fix this bug")
    assert IntentEngine.is_action_request("Let's build the frontend")
    assert IntentEngine.is_action_request("Could you inspect the logs?")


def test_intent_engine_pure_informational_queries():
    # Pure informational questions should NOT be flagged as mandatory action requests
    assert not IntentEngine.is_action_request("what is an async generator in Python?")
    assert not IntentEngine.is_action_request("why did you choose LanceDB over Pinecone?")
    assert not IntentEngine.is_action_request("how does token counting work?")
    assert not IntentEngine.is_action_request("who is the project owner?")
    assert not IntentEngine.is_action_request("can you explain the difference between processes and threads?")
    assert not IntentEngine.is_action_request("tell me about the architecture")


def test_intent_engine_compound_questions_with_actions():
    # Question followed by explicit action directive
    assert IntentEngine.is_action_request("How does auth work? Find the auth file.")
    assert IntentEngine.is_action_request("What is failing in the build? Run pytest to check.")


def test_intent_engine_detect_false_browser_refusal():
    refusal_1 = "I cannot browse the web as an AI language model."
    refusal_2 = "I don't have access to a browser to visit websites."
    refusal_3 = "I am unable to open a browser."

    assert IntentEngine.detect_false_refusal(refusal_1) is not None
    assert "False Refusal / Missing Browser Tool Call" in IntentEngine.detect_false_refusal(refusal_1)
    assert IntentEngine.detect_false_refusal(refusal_2) is not None
    assert IntentEngine.detect_false_refusal(refusal_3) is not None

    # Normal response without refusal
    assert IntentEngine.detect_false_refusal("I navigated to google.com and found the results.") is None


def test_intent_engine_detect_unexecuted_promise():
    promise_1 = "I'll open the browser and search for that right away."
    promise_2 = "Let me check the database configuration for you."
    promise_3 = "I will hire a Coder to implement this function."

    # Without tool call: flagged!
    assert IntentEngine.detect_unexecuted_promise(promise_1, has_tool_call=False) is not None
    assert IntentEngine.detect_unexecuted_promise(promise_2, has_tool_call=False) is not None
    assert IntentEngine.detect_unexecuted_promise(promise_3, has_tool_call=False) is not None
    assert IntentEngine.detect_unexecuted_promise("On it — opening a browser to search for the latest news.", has_tool_call=False) is not None
    assert IntentEngine.detect_unexecuted_promise("Let me check the browser snapshot to see what news appeared.", has_tool_call=False) is not None

    # With tool call: NOT flagged!
    assert IntentEngine.detect_unexecuted_promise(promise_1, has_tool_call=True) is None
    assert IntentEngine.detect_unexecuted_promise(promise_2, has_tool_call=True) is None
    assert IntentEngine.detect_unexecuted_promise(promise_3, has_tool_call=True) is None
    assert IntentEngine.detect_unexecuted_promise("On it — opening a browser to search for the latest news.", has_tool_call=True) is None


def test_intent_engine_action_requests_with_mentions_and_browser():
    assert IntentEngine.is_action_request("open a web browser and search for latest news using the browser @Archer")
    assert IntentEngine.is_action_request("@Nova search for python docs online")
    assert IntentEngine.is_action_request("open the dashboard preview @Coder")
