"""
# backend/tests/test_semantic_router.py

Unit tests for Carole.ai's native Semantic Router and IntentEngine.
"""

import pytest
from core.agent.semantic_router import semantic_router, RouteMatch
from core.agent.intent_engine import IntentEngine


def test_semantic_router_capability_queries():
    """Test that capability and tool permission queries are correctly routed."""
    queries = [
        "do you have access to write something into memory tool ?",
        "can you write to memory?",
        "what tools do you have access to?",
        "do you have access to the browser tool?",
        "are you allowed to edit files in this project?",
        "can you tell me what you are able to do?",
    ]
    for q in queries:
        match = semantic_router.route(q)
        assert match is not None, f"Query '{q}' should match a route"
        assert match.name == "capability_inquiry", f"Query '{q}' matched {match.name}, expected capability_inquiry"
        assert match.score >= match.threshold


def test_semantic_router_action_commands():
    """Test that imperative action commands are routed to imperative_action."""
    actions = [
        "write a python script to test the database",
        "create the frontend landing page in index.html",
        "run pytest on the test suite",
        "edit backend/main.py to add the new endpoint",
        "search google for the latest react release",
        "fix the bug in auth login handler",
    ]
    for a in actions:
        match = semantic_router.route(a)
        assert match is not None, f"Action '{a}' should match a route"
        assert match.name == "imperative_action", f"Action '{a}' matched {match.name}, expected imperative_action"
        assert match.score >= match.threshold


def test_semantic_router_greetings_and_chitchat():
    """Test that greetings and social pleasantries match chitchat_greeting."""
    greetings = [
        "hello",
        "hey there",
        "good morning",
        "thanks for the help",
        "thank you very much",
    ]
    for g in greetings:
        match = semantic_router.route(g)
        assert match is not None, f"Greeting '{g}' should match a route"
        assert match.name == "chitchat_greeting", f"Greeting '{g}' matched {match.name}, expected chitchat_greeting"


def test_semantic_router_informational_questions():
    """Test that technical conceptual questions match informational_question."""
    questions = [
        "how does authentication work in this app?",
        "what is the difference between facts and memory?",
        "explain how carole_dir is constructed",
        "where are temporary files stored?",
    ]
    for q in questions:
        match = semantic_router.route(q)
        assert match is not None, f"Question '{q}' should match a route"
        assert match.name == "informational_question", f"Question '{q}' matched {match.name}, expected informational_question"


def test_intent_engine_is_action_request():
    """Verify that IntentEngine uses the Semantic Router and returns correct booleans."""
    # Capability queries should NOT mandate action
    assert not IntentEngine.is_action_request("do you have access to write something into memory tool ?")
    assert not IntentEngine.is_action_request("can you write to memory?")
    assert not IntentEngine.is_action_request("what tools do you have?")

    # Greetings should NOT mandate action
    assert not IntentEngine.is_action_request("hello")
    assert not IntentEngine.is_action_request("hey there")

    # Informational questions should NOT mandate action
    assert not IntentEngine.is_action_request("what is carole_dir ?")
    assert not IntentEngine.is_action_request("how does authentication work?")

    # Action commands MUST mandate action
    assert IntentEngine.is_action_request("write a python script to test the database")
    assert IntentEngine.is_action_request("create index.html")
    assert IntentEngine.is_action_request("run pytest on the test suite")
