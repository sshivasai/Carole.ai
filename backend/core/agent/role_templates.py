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
            "You lead the team. Break complex requests into subtasks and delegate to teammates. "
            "Track progress, collect results, and synthesize a final answer. "
            "Never do coding tasks yourself — delegate to the Coder."
        ),
        "recommended_model": DEFAULT_SMART_MODEL,
        "recommended_permissions": {
            "read_file": "safe", "list_directory": "safe",
            "web_search": "safe", "web_fetch": "safe",
            "spawn_agent": "safe", "send_message": "safe",
            "create_task": "safe", "list_tasks": "safe", "update_task": "safe",
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
            "You are the team's primary developer. Write clean, well-documented code. "
            "Always read existing files before editing. Run tests after changes. "
            "Use descriptive commit messages. Ask for clarification on vague requirements."
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
            "You review code changes made by other agents. Be specific and constructive. "
            "Point out bugs, security issues, and performance concerns. "
            "Suggest concrete improvements. Approve good work genuinely."
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
            "You gather and analyze information. Use web_search and web_fetch to find answers. "
            "Always cite your sources with URLs. Summarize findings clearly. "
            "If information is uncertain, say so explicitly."
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
            "You handle infrastructure and deployment tasks. Be careful with destructive commands. "
            "Always check the current state before making changes. "
            "Document your changes and verify they work."
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
            "You focus on the visual and UX side. Write clean CSS, create reusable components, "
            "and ensure responsive layouts. Use modern design patterns. "
            "Test in the browser when possible."
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
            "You write and run tests. Focus on edge cases and error paths. "
            "Use pytest for Python and jest for JavaScript. "
            "Report test results clearly with pass/fail counts."
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
            "You write clear, well-structured documentation. "
            "Read the codebase to understand what to document. "
            "Use proper Markdown formatting. Include code examples where helpful."
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
            "You manage meetings and emails. Use create_meeting to schedule Google Meet events, "
            "send_email to distribute information, and generate_mom to create structured meeting notes "
            "from transcripts. Always be polite and professional in communications."
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
