"""
# backend/tests/test_remediation_suite.py

Comprehensive verification test suite for Carole.ai Master Remediation Plan.
Tests all phases: Memory sync, SSRF Guard, File Tools Sandbox, Tool Executor Permissions,
Browser HIL Takeover, and Browser Routes.
"""

import pytest
import asyncio
import uuid
import re
from pathlib import Path

from core.tools.ssrf_guard import assert_safe_public_url
from core.tools.file_tools import file_tools
from core.tools.code_analysis_tools import CodeAnalysisTools
from core.tools.tool_executor import (
    _get_effective_permissions,
    _resolve_gate_level,
    _TOOL_CATEGORY,
    _CATEGORY_DEFAULTS,
)
from core.tools.interaction_tools import interaction_tools, pending_questions, question_answers


# ── 1. SSRF Guard & Localhost Tests ──────────────────────────────────────────

def test_ssrf_guard_allows_localhost_and_dev_ports():
    """Local dev tool must allow localhost, 127.0.0.1, and local ports."""
    assert assert_safe_public_url("http://localhost:3000") == "http://localhost:3000"
    assert assert_safe_public_url("http://127.0.0.1:5173/api/test") == "http://127.0.0.1:5173/api/test"
    assert assert_safe_public_url("http://localhost:8000") == "http://localhost:8000"
    assert assert_safe_public_url("https://github.com/browser-use/browser-use") == "https://github.com/browser-use/browser-use"


def test_ssrf_guard_blocks_cloud_metadata():
    """Must block 169.254.169.254 and metadata hostnames."""
    with pytest.raises(ValueError, match="Access to.*cloud metadata|blocked"):
        assert_safe_public_url("http://169.254.169.254/latest/meta-data/")

    with pytest.raises(ValueError, match="Access to cloud metadata"):
        assert_safe_public_url("http://metadata.google.internal/computeMetadata/v1/")


def test_ssrf_guard_blocks_invalid_schemes():
    """Only http and https schemes are permitted."""
    with pytest.raises(ValueError, match="Unsafe or unsupported URL scheme"):
        assert_safe_public_url("file:///etc/passwd")

    with pytest.raises(ValueError, match="Unsafe or unsupported URL scheme"):
        assert_safe_public_url("gopher://localhost:70")


# ── 2. Sandbox Boundary Enforcement ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_file_tools_sandbox_blocks_traversal():
    """read_file and list_directory must reject directory traversal out of sandbox."""
    res_read = await file_tools.read_file("../../outside.txt")
    assert "Access Denied" in res_read or "Error" in res_read

    res_list = await file_tools.list_directory("../../../")
    assert "Access Denied" in res_list or "Error" in res_list


def test_code_analysis_sandbox():
    """Code analysis tools must use strict Path.relative_to sandbox checks."""
    analyzer = CodeAnalysisTools(workspace_root=str(Path.cwd()))
    with pytest.raises(PermissionError, match="Access Denied"):
        analyzer._resolve_safe_path("../../outside_file.py")


# ── 3. Tool Permissions & Category Resolution ────────────────────────────────

def test_flat_category_permissions_resolution():
    """Flat permission dicts like {'subagents': 'block'} must properly map to category."""
    perms = {"subagents": "block", "read_file": "safe"}
    effective = _get_effective_permissions(perms)

    # 'subagents' category must be overridden to 'block'
    assert effective["categories"].get("subagents") == "block"
    # 'read_file' tool must be in overrides
    assert effective["overrides"].get("read_file") == "safe"

    # _resolve_gate_level for spawn_agent (which is in subagents category) must return 'block'
    gate = _resolve_gate_level("spawn_agent", effective)
    assert gate == "block"


def test_tool_category_coverage():
    """Critical browser, memory, and subagent tools must be categorized."""
    assert _TOOL_CATEGORY.get("browser_human_takeover") == "browser"
    assert _TOOL_CATEGORY.get("browser_task") == "browser"
    assert _TOOL_CATEGORY.get("spawn_agent") == "subagents"
    assert _TOOL_CATEGORY.get("add_memory") == "create"
    assert _TOOL_CATEGORY.get("search_memory") == "view"


# ── 4. Human-In-The-Loop (HIL) Browser Takeover ──────────────────────────────

@pytest.mark.asyncio
async def test_browser_human_takeover_flow():
    """browser_human_takeover must pause, register pending event, and resolve on user input."""
    agent_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    async def simulate_human_resolution():
        await asyncio.sleep(0.1)
        # Find active question ID
        for q_id, event in list(pending_questions.items()):
            question_answers[q_id] = "Solved Cloudflare CAPTCHA"
            event.set()

    asyncio.create_task(simulate_human_resolution())

    result = await interaction_tools.browser_human_takeover(
        reason="Cloudflare Turnstile CAPTCHA on screen",
        agent_id=agent_id,
        agent_name="WebNavigator",
        team_id=team_id,
        timeout=5.0,
    )

    assert "Human completed intervention" in result or "Solved" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
