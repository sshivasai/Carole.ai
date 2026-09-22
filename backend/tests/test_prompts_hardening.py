import json
import pytest
from pathlib import Path
from core.prompts import load_prompts, get_prompt, load_default_prompts
from core.config import (
    _PROMPT_ALIASES,
    BROWSER_AGENT_SYSTEM_PROMPT,
    CONSOLIDATION_PROMPT,
)
from core.agent.prompt_blocks import get_block, list_blocks
from core.memory.auto_dream import dream_worker
from core.tools.browser_agent import _extract_json, BROWSER_AGENT_SYSTEM_PROMPT as BROWSER_FALLBACK


def test_prompts_json_schema_and_keys():
    """Verify core/defaults/prompts.json is valid JSON and contains all critical slugs."""
    defaults = load_default_prompts()
    assert isinstance(defaults, dict)
    assert len(defaults) >= 33

    critical_keys = [
        "personality.professional",
        "system.behavioral_rules",
        "system.tool_use",
        "system.reasoning_rules",
        "system.coordinator_directives",
        "system.judge",
        "system.consolidation",
        "system.browser_agent",
        "block.browser",
        "block.scratchpads",
        "block.docs",
        "block.workspace_paths",
        "block.scheduler",
    ]
    for key in critical_keys:
        assert key in defaults, f"Missing critical prompt slug: {key}"
        assert len(defaults[key].strip()) > 50, f"Prompt {key} is unexpectedly empty"


def test_tool_instructions_use_discovery_and_current_permissions():
    defaults = load_default_prompts()
    for key in ["role.orchestrator", "system.reasoning_rules", "system.tool_use"]:
        assert "fetch_tool_schemas" in defaults[key]
        assert "full access" not in defaults[key].lower()
    assert "AN ORCHESTRATOR NEVER WRITES" not in defaults["system.coordinator_directives"]


def test_system_consolidation_alignment_with_auto_dream():
    """Verify system.consolidation instructions match auto_dream parser expectations."""
    prompt = get_prompt("system.consolidation")
    assert "{conversation}" in prompt
    assert "NO_LESSONS" in prompt
    assert "CRITICAL FORMAT RULES" in prompt
    assert "```json" in prompt

    # Verify auto_dream _is_no_lessons handles specified formats
    assert dream_worker._is_no_lessons("NO_LESSONS")
    assert dream_worker._is_no_lessons("no_lessons")
    assert dream_worker._is_no_lessons("```\nNO_LESSONS\n```")
    assert dream_worker._is_no_lessons("```json\nNO_LESSONS\n```")
    assert not dream_worker._is_no_lessons("I found 3 lessons today.")

    # Verify auto_dream _parse_lessons handles fenced JSON array
    fenced_output = (
        "```json\n"
        "[\n"
        '  {"category": "RULES", "task_summary": "Theme rule", "content": "Always use dark theme."},\n'
        '  {"category": "ENTITY_FACT", "key": "user_role", "value": "Admin"}\n'
        "]\n"
        "```"
    )
    lessons, facts = dream_worker._parse_lessons(fenced_output)
    assert len(lessons) == 1
    assert lessons[0] == ("Theme rule", "[RULES] Always use dark theme.")
    assert len(facts) == 1
    assert facts[0] == ("user_role", "Admin")

    # Verify empty JSON array
    empty_output = "```json\n[]\n```"
    empty_lessons, empty_facts = dream_worker._parse_lessons(empty_output)
    assert empty_lessons == []
    assert empty_facts == []


def test_system_browser_agent_alignment_with_browser_agent():
    """Verify system.browser_agent instructions match browser_agent parser & execution."""
    prompt = get_prompt("system.browser_agent")
    assert "browser_human_takeover" in prompt
    assert "```json" in prompt
    assert "navigate" in prompt
    assert "click" in prompt
    assert "type" in prompt
    assert "select" in prompt
    assert "check" in prompt
    assert "uncheck" in prompt
    assert "wait" in prompt

    # Verify browser_agent _extract_json parses model responses adhering to prompt
    action_response = (
        "```json\n"
        '{"thought": "Need to click submit", "done": false, "action": {"type": "click", "ref": 5}}\n'
        "```"
    )
    parsed = _extract_json(action_response)
    assert parsed is not None
    assert parsed.get("done") is False
    assert parsed.get("action", {}).get("type") == "click"
    assert parsed.get("action", {}).get("ref") == 5

    finish_response = (
        "```json\n"
        '{"thought": "Goal accomplished", "done": true, "success": true, "summary": "Found the pricing."}\n'
        "```"
    )
    parsed_finish = _extract_json(finish_response)
    assert parsed_finish is not None
    assert parsed_finish.get("done") is True
    assert parsed_finish.get("success") is True
    assert "pricing" in parsed_finish.get("summary")


def test_block_browser_alignment():
    """Verify block.browser includes browser_human_takeover and integrates into prompt_blocks."""
    block = get_block("browser")
    assert block is not None
    assert "browser_human_takeover" in block
    assert "CAPTCHA" in block
    assert "browser_task" in block


def test_config_prompt_alias_browser_agent():
    """Verify BROWSER_AGENT_SYSTEM_PROMPT is accessible via core.config and maps to system.browser_agent."""
    assert "BROWSER_AGENT_SYSTEM_PROMPT" in _PROMPT_ALIASES
    assert _PROMPT_ALIASES["BROWSER_AGENT_SYSTEM_PROMPT"] == "system.browser_agent"

    from core.config import BROWSER_AGENT_SYSTEM_PROMPT as resolved
    assert resolved == get_prompt("system.browser_agent")
    assert "browser_human_takeover" in resolved
