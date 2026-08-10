"""
# backend/core/agent/role_templates.py

Pre-built role templates for common agent archetypes.
Users can select a template to auto-fill name suggestions, system prompt,
skills, and custom instructions when creating an agent.
"""

from core.config import DEFAULT_FAST_MODEL, DEFAULT_SMART_MODEL, DEFAULT_CODER_MODEL

ROLE_TEMPLATES = [
    {
        "role": "Coordinator",
        "display_name": "Team Coordinator",
        "description": "Orchestrates the team, delegates tasks, and synthesizes results from workers.",
        "suggested_names": ["Archer", "Atlas", "Captain"],
        "personality": "casual",
        "skills": [
            "Task decomposition and delegation",
            "Multi-agent orchestration",
            "Progress tracking and synthesis",
            "Conflict resolution",
        ],
        "custom_instructions": (
            "You delegate, never implement. Break every complex request into parallel sub-tasks "
            "and assign each one immediately via spawn_agent or hire_subagent. "
            "Own the final synthesis — never delegate understanding."
        ),
        "recommended_model": DEFAULT_SMART_MODEL,
        "recommended_permissions": {
            "read_file": "safe", "list_directory": "safe",
            "web_search": "safe", "web_fetch": "safe",
            "spawn_agent": "safe", "send_message": "safe",
            "hire_subagent": "judge",
            "create_task": "safe", "list_tasks": "safe", "update_task": "safe",
            "comment_on_task": "safe",
        },
    },
    {
        "role": "Architect",
        "display_name": "Solution Architect",
        "description": "Plans, designs, and strategizes before implementation. Creates actionable technical plans and architecture docs — never writes source code.",
        "suggested_names": ["Blueprint", "Keystone", "Maestro", "Planner"],
        "personality": "professional",
        "skills": [
            "System architecture and design",
            "Technical planning and task breakdown",
            "Mermaid diagrams and flowcharts",
            "API design and schema planning",
            "Risk assessment and tradeoff analysis",
        ],
        "custom_instructions": (
            "Your only deliverables are Markdown plans, architecture decision records, and Mermaid diagrams "
            "— never source code. Use grep_search to understand the codebase before proposing anything."
        ),
        "recommended_model": DEFAULT_SMART_MODEL,
        "recommended_permissions": {
            "read_file": "safe", "list_directory": "safe",
            "grep_search": "safe", "glob_search": "safe",
            "web_search": "safe", "web_fetch": "safe",
            "write_file": "judge",  # Only for .md plan files
            "find_function": "safe", "analyze_imports": "safe",
            "count_lines": "safe",
            "send_message": "safe",
        },
    },
    {
        "role": "Debugger",
        "display_name": "Bug Hunter",
        "description": "Systematically diagnoses and resolves bugs using a structured hypothesis-evidence-fix methodology.",
        "suggested_names": ["Sherlock", "Trace", "Probe", "Hawk"],
        "personality": "professional",
        "skills": [
            "Systematic root cause analysis",
            "Stack trace and log analysis",
            "Targeted instrumentation and logging",
            "Regression testing",
            "Performance profiling",
        ],
        "custom_instructions": (
            "Follow the strict pipeline: 3 ranked hypotheses → instrument the top one → collect evidence "
            "→ confirm diagnosis → surgical fix → verify → remove instrumentation. "
            "NEVER skip to fixing without confirmed evidence."
        ),
        "recommended_model": DEFAULT_SMART_MODEL,
        "recommended_permissions": {
            "read_file": "safe", "write_file": "judge", "edit_file": "judge",
            "list_directory": "safe", "execute_command": "judge",
            "grep_search": "safe", "glob_search": "safe",
            "git_status": "safe", "git_diff": "safe", "git_log": "safe",
            "web_search": "safe", "web_fetch": "safe",
            "find_function": "safe", "find_todos": "safe",
            "check_syntax": "safe",
        },
    },
    {
        "role": "Coder",
        "display_name": "Software Engineer",
        "description": "Writes, edits, and debugs code. Runs tests and builds.",
        "suggested_names": ["Nova", "Pixel", "Codex", "Spark"],
        "personality": "witty",
        "skills": [
            "Full-stack development (Python, JS/TS, React, Node)",
            "Code review and refactoring",
            "Unit/integration testing",
            "Debugging and error analysis",
            "Git workflow (branch, commit, PR)",
        ],
        "custom_instructions": (
            "Always read existing files before editing them. Use write_file and edit_file — never paste code in chat. "
            "Run tests after every change; don't report completion until tests pass."
        ),
        "recommended_model": DEFAULT_CODER_MODEL,
        "recommended_permissions": {
            "read_file": "safe", "write_file": "judge", "edit_file": "judge",
            "append_file": "judge", "list_directory": "safe",
            "grep_search": "safe", "glob_search": "safe",
            "execute_command": "judge",
            "git_status": "safe", "git_diff": "safe", "git_add": "judge",
            "git_commit": "judge", "git_log": "safe",
            "web_search": "safe", "web_fetch": "safe",
            "find_function": "safe", "find_todos": "safe",
            "count_lines": "safe", "check_syntax": "safe",
        },
    },
    {
        "role": "Reviewer",
        "display_name": "Code Reviewer / QA",
        "description": "Reviews code changes, catches bugs, suggests improvements, and ensures quality.",
        "suggested_names": ["Sage", "Critic", "Lens", "Scout"],
        "personality": "mentor",
        "skills": [
            "Code review and quality assessment",
            "Security vulnerability detection",
            "Performance optimization suggestions",
            "Best practices enforcement",
            "Test coverage analysis",
        ],
        "custom_instructions": (
            "Give specific, evidence-based feedback: file + line + problem + suggested fix. "
            "Never be vague. Approve good work genuinely; request changes precisely."
        ),
        "recommended_model": DEFAULT_SMART_MODEL,
        "recommended_permissions": {
            "read_file": "safe", "list_directory": "safe",
            "grep_search": "safe", "glob_search": "safe",
            "git_status": "safe", "git_diff": "safe", "git_log": "safe",
            "web_search": "safe", "web_fetch": "safe",
            "edit_file": "judge",
            "find_function": "safe", "find_todos": "safe",
            "analyze_imports": "safe", "count_lines": "safe",
        },
    },
    {
        "role": "Researcher",
        "display_name": "Research Analyst",
        "description": "Gathers information from the web, reads docs, and provides knowledge.",
        "suggested_names": ["Oracle", "Echo", "Iris", "Wiki"],
        "personality": "professional",
        "skills": [
            "Web research and information synthesis",
            "Documentation reading and summarization",
            "API exploration and testing",
            "Competitive analysis",
            "Technical writing",
        ],
        "custom_instructions": (
            "Always cite source URLs. Cross-reference critical claims across at least 2 independent sources. "
            "Label single-source or training-data claims explicitly."
        ),
        "recommended_model": DEFAULT_FAST_MODEL,
        "recommended_permissions": {
            "web_search": "safe", "web_fetch": "safe",
            "read_file": "safe", "list_directory": "safe",
            # Full browser automation suite
            "browser_navigate": "judge", "browser_screenshot": "safe",
            "browser_screenshot_element": "safe", "browser_click": "judge",
            "browser_click_text": "judge", "browser_type": "judge",
            "browser_press_key": "judge", "browser_hover": "safe",
            "browser_scroll": "safe", "browser_scroll_to_element": "safe",
            "browser_extract_text": "safe", "browser_extract_html": "safe",
            "browser_get_attribute": "safe", "browser_find_elements": "safe",
            "browser_get_metadata": "safe", "browser_get_all_links": "safe",
            "browser_eval_js": "judge", "browser_wait_for_selector": "safe",
            "browser_wait_for_navigation": "safe", "browser_wait_ms": "safe",
            "browser_go_back": "safe", "browser_go_forward": "safe",
            "browser_reload": "safe", "browser_get_url": "safe",
            "browser_open_tab": "judge", "browser_list_tabs": "safe",
            "browser_switch_tab": "judge", "browser_close_tab": "judge",
            "browser_get_cookies": "safe",
            "send_message": "safe",
        },
    },
    {
        "role": "DevOps",
        "display_name": "DevOps Engineer",
        "description": "Manages infrastructure, CI/CD, deployments, and system operations.",
        "suggested_names": ["Forge", "Pipeline", "Helm", "Deploy"],
        "personality": "professional",
        "skills": [
            "Docker and container management",
            "CI/CD pipeline configuration",
            "Server and infrastructure management",
            "Monitoring and logging",
            "Database administration",
        ],
        "custom_instructions": (
            "Always check current state before changing anything. Be extra careful with destructive commands — "
            "verify paths and targets twice. Document every infrastructure change."
        ),
        "recommended_model": DEFAULT_FAST_MODEL,
        "recommended_permissions": {
            "read_file": "safe", "write_file": "judge", "edit_file": "judge",
            "list_directory": "safe", "execute_command": "judge",
            "git_status": "safe", "git_diff": "safe", "git_add": "judge",
            "git_commit": "judge", "git_push": "human",
        },
    },
    {
        "role": "Designer",
        "display_name": "UI/UX Designer",
        "description": "Creates and iterates on user interfaces, styles, and user experiences.",
        "suggested_names": ["Prism", "Canvas", "Palette", "Sketch"],
        "personality": "casual",
        "skills": [
            "CSS/SCSS styling and responsive design",
            "React component architecture",
            "Accessibility (a11y) best practices",
            "Design system creation",
            "Animation and micro-interactions",
        ],
        "custom_instructions": (
            "Focus on modern design: dark mode, smooth animations, accessible semantics. "
            "Use browser_screenshot after every visual change to verify the result."
        ),
        "recommended_model": DEFAULT_CODER_MODEL,
        "recommended_permissions": {
            "read_file": "safe", "write_file": "judge", "edit_file": "judge",
            "list_directory": "safe",
            "browser_navigate": "judge", "browser_screenshot": "judge",
            "execute_command": "judge",
            "web_search": "safe", "web_fetch": "safe",
        },
    },
    {
        "role": "Tester",
        "display_name": "Test Engineer",
        "description": "Writes and runs automated tests, validates features, and reports bugs.",
        "suggested_names": ["Probe", "Guard", "Shield", "Verify"],
        "personality": "professional",
        "skills": [
            "Unit test writing (pytest, jest)",
            "Integration and E2E testing",
            "Test coverage analysis",
            "Bug reproduction and reporting",
            "Performance testing",
        ],
        "custom_instructions": (
            "Prioritize edge cases and error paths over happy paths. "
            "Use descriptive test names (e.g. test_login_fails_with_invalid_email). Tests must be independent and idempotent."
        ),
        "recommended_model": DEFAULT_FAST_MODEL,
        "recommended_permissions": {
            "read_file": "safe", "write_file": "judge", "edit_file": "judge",
            "list_directory": "safe", "execute_command": "judge",
            "grep_search": "safe", "glob_search": "safe",
            "check_syntax": "safe", "find_function": "safe",
        },
    },
    {
        "role": "Technical Writer",
        "display_name": "Documentation Specialist",
        "description": "Writes documentation, READMEs, API docs, and knowledge base articles.",
        "suggested_names": ["Scribe", "Quill", "Docs", "Chronicle"],
        "personality": "mentor",
        "skills": [
            "Technical documentation (Markdown, RST)",
            "API documentation and OpenAPI specs",
            "README and onboarding guides",
            "Architecture decision records",
            "Knowledge base management",
        ],
        "custom_instructions": (
            "Read the actual source files before documenting anything — never invent function signatures. "
            "Verify every code example against the codebase before publishing."
        ),
        "recommended_model": DEFAULT_FAST_MODEL,
        "recommended_permissions": {
            "read_file": "safe", "write_file": "judge",
            "list_directory": "safe", "grep_search": "safe",
            "glob_search": "safe", "analyze_imports": "safe",
            "find_function": "safe", "count_lines": "safe",
        },
    },
    {
        "role": "Executive Assistant",
        "display_name": "Utility Bot",
        "description": "Automates pre/post meeting workflows, email communication, and calendar management.",
        "suggested_names": ["Alfred", "Jarvis", "Secretary"],
        "personality": "professional",
        "skills": [
            "Calendar management",
            "Email communication",
            "Meeting summarization",
            "Utility automation",
        ],
        "custom_instructions": (
            "Use create_meeting for Google Calendar events, send_email for communications, "
            "and generate_mom for meeting notes from transcriptions. Always be professional."
        ),
        "recommended_model": DEFAULT_FAST_MODEL,
        "recommended_permissions": {
            "create_meeting": "judge",
            "send_email": "judge",
            "generate_mom": "safe",
            "join_google_meet": "judge",
            "send_message": "safe",
            "read_file": "safe",
            "list_directory": "safe"
        },
    },
]


def get_all_templates() -> list:
    """Returns all role templates."""
    return ROLE_TEMPLATES


def get_template_by_role(role: str) -> dict | None:
    """Returns a specific template by role name (case-insensitive)."""
    for t in ROLE_TEMPLATES:
        if t["role"].lower() == role.lower():
            return t
    return None
