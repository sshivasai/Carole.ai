"""
# backend/core/tools/tool_executor.py

Manages secure tool execution, permission gating, and human-in-the-loop approvals.
Delegates all tool lookups to the ToolRegistry and emits file_change / tool events
to the EventBus for live UI streaming.

Permission Levels:
1. "safe" - Instantly executes.
2. "judge" - Pauses and requests an async verification appraisal from the Judge AI.
3. "human" - Blocks the execution flow until the human approves via the REST API.
"""

import uuid
import asyncio
import logging
from typing import Dict, Any

from core.chat.event_bus import event_bus
from core.tools.tool_registry import ToolRegistry, ToolSpec
from core.tools.file_tools import file_tools, FileChangeResult
from core.tools.shell_tools import shell_tools
from core.tools.git_tools import git_tools
from core.tools.web_tools import web_tools
from core.tools.agent_tools import agent_tools
from core.tools.browser_tool import browser_tool
from core.tools.interaction_tools import interaction_tools
from core.tools.code_analysis_tools import code_analysis_tools
from core.tools.memory_tools import memory_tools
from core.tools.meeting_tool import meeting_tool
from core.tools.google_workspace_tools import create_meeting, send_email
from core.judge.judge_evaluator import judge_evaluator
from core.config import APPROVAL_TIMEOUT_SECS

from core.tools.context import ToolExecutionContext, ToolPermissionContext

logger = logging.getLogger("carole.tool_executor")

# Tools that mutate files but are safe to auto-approve when the target is a
# documentation file (markdown / plain-text notes like implementation.md or
# taskstracker.md). Letting agents create and edit docs without Judge review
# keeps planning/notetaking frictionless — these files cannot execute and are
# sandboxed to the workspace, so the risk surface is minimal.
_DOC_WRITE_TOOLS = {"write_file", "edit_file", "append_file"}
_DOC_EXTENSIONS = (".md", ".markdown", ".txt")


def _is_doc_write(tool_name: str, arguments: Dict[str, Any]) -> bool:
    """True when a file-write tool targets a documentation path (.md/.txt).

    Used to fast-path doc writes past the Judge gate so agents can keep
    implementation.md / taskstracker.md style notes without approval friction.
    """
    if tool_name not in _DOC_WRITE_TOOLS:
        return False
    rel = arguments.get("relative_path") or arguments.get("path")
    if not isinstance(rel, str) or not rel:
        return False
    return rel.lower().endswith(_DOC_EXTENSIONS)


# Global dictionaries to manage pending human approvals across concurrent agent loops
pending_approvals: Dict[str, asyncio.Event] = {}
approval_results: Dict[str, bool] = {}  # Maps tx_id to True (Approved) or False (Denied)

# Idempotency guard — ensures register_builtin_tools() is a no-op if called twice
_builtins_registered: bool = False


def register_builtin_tools():
    """Registers all built-in tools with the ToolRegistry at startup.
    Called once from main.py lifespan."""
    global _builtins_registered
    if _builtins_registered:
        logger.debug("[ToolRegistry] Built-in tools already registered — skipping.")
        return
    _builtins_registered = True

    builtins = [
        # ---- Filesystem ----
        ToolSpec("read_file", "Read the full contents of a file. You MUST call this before edit_file to see the exact current content. For very large files, consider grep_search first to find the relevant section.", "filesystem",
                 {"relative_path": {"type": "string", "required": True}},
                 "safe", _wrap_read_file),
        ToolSpec("write_file", "Create a new file or completely overwrite an existing one. WARNING: This replaces the ENTIRE file contents. To change only specific lines, use edit_file instead. For Markdown/text docs (.md, .txt), writes are auto-approved (no Judge review needed).", "filesystem",
                 {"relative_path": {"type": "string", "required": True},
                  "content": {"type": "string", "required": True}},
                 "judge", _wrap_write_file),
        ToolSpec("edit_file", "Replace a specific block of text in a file. IMPORTANT: You MUST read_file FIRST to see the exact current content, then provide the EXACT target_content that exists in the file. Partial or approximate matches will fail.", "filesystem",
                 {"relative_path": {"type": "string", "required": True},
                  "target_content": {"type": "string", "required": True, "description": "The exact text block currently in the file that you want to replace. Must match character-for-character."},
                  "replacement_content": {"type": "string", "required": True, "description": "The new text to replace target_content with."}},
                 "judge", _wrap_edit_file),
        ToolSpec("list_directory", "List files and directories at a path", "filesystem",
                 {"relative_path": {"type": "string", "required": False}},
                 "safe", _wrap_list_directory),
        ToolSpec("append_file", "Append content to the end of a file", "filesystem",
                 {"relative_path": {"type": "string", "required": True},
                  "content": {"type": "string", "required": True}},
                 "judge", _wrap_append_file),
        ToolSpec("delete_file", "Delete a file from the workspace", "filesystem",
                 {"relative_path": {"type": "string", "required": True}},
                 "human", _wrap_delete_file),
        ToolSpec("grep_search", "Search file contents for a regex pattern", "search",
                 {"pattern": {"type": "string", "required": True},
                  "path": {"type": "string", "required": False},
                  "case_sensitive": {"type": "boolean", "required": False}},
                 "safe", _wrap_grep_search),
        ToolSpec("glob_search", "Find files matching a glob pattern (e.g. **/*.py)", "search",
                 {"pattern": {"type": "string", "required": True},
                  "path": {"type": "string", "required": False}},
                 "safe", _wrap_glob_search),

        # ---- Shell ----
        ToolSpec("execute_command", "Execute a shell command in the workspace directory. Returns stdout+stderr (max 60s timeout by default). Use 'cwd' param to run in a subdirectory (e.g. 'frontend') instead of chaining cd commands. IMPORTANT: Long-running commands (servers, watchers) will timeout after 60s — increase timeout if needed. For Git operations, prefer the git_* tools over raw git commands.", "shell",
                 {"command": {"type": "string", "required": True},
                  "timeout": {"type": "number", "required": False, "description": "Max seconds to wait (default 60)"},
                  "cwd": {"type": "string", "required": False, "description": "Subdirectory to run the command in, relative to workspace root (e.g. 'frontend', 'backend/core')"}},
                 "judge", _wrap_execute_command),

        # ---- Git ----
        ToolSpec("git_status", "Show current git status", "git", {}, "safe", _wrap_git_status),
        ToolSpec("git_diff", "Show uncommitted changes", "git",
                 {"staged": {"type": "boolean", "required": False}}, "safe", _wrap_git_diff),
        ToolSpec("git_add", "Stage files for commit", "git",
                 {"paths": {"type": "string", "required": False}}, "judge", _wrap_git_add),
        ToolSpec("git_commit", "Create a commit", "git",
                 {"message": {"type": "string", "required": True}}, "judge", _wrap_git_commit),
        ToolSpec("git_log", "Show recent commit history", "git",
                 {"count": {"type": "number", "required": False}}, "safe", _wrap_git_log),
        ToolSpec("git_checkout", "Switch or create a branch", "git",
                 {"branch": {"type": "string", "required": True},
                  "create": {"type": "boolean", "required": False}}, "judge", _wrap_git_checkout),
        ToolSpec("git_push", "Push current branch to remote", "git",
                 {"remote": {"type": "string", "required": False},
                  "branch": {"type": "string", "required": False}}, "human", _wrap_git_push),
        ToolSpec("git_pull", "Pull latest changes from the remote (git fetch + merge). Use before editing shared branches.", "git",
                 {"remote": {"type": "string", "required": False, "description": "Remote name (default: origin)"},
                  "branch": {"type": "string", "required": False, "description": "Branch to pull (default: current tracking branch)"}},
                 "judge", _wrap_git_pull),
        ToolSpec("git_branch", "List all local branches (with last commit info). Set all=true to include remote-tracking branches.", "git",
                 {"all": {"type": "boolean", "required": False, "description": "true to include remote branches"}},
                 "safe", _wrap_git_branch),
        ToolSpec("git_stash", "Stash or unstash changes (push/pop/list/drop)", "git",
                 {"action": {"type": "string", "required": False},
                  "message": {"type": "string", "required": False}}, "judge", _wrap_git_stash),
        ToolSpec("git_clone", "Clone a repository", "git",
                 {"url": {"type": "string", "required": True},
                  "directory": {"type": "string", "required": False}}, "human", _wrap_git_clone),

        # ---- Filesystem extras ----
        ToolSpec("copy_file", "Copy a file to a new location", "filesystem",
                 {"source": {"type": "string", "required": True},
                  "destination": {"type": "string", "required": True}}, "judge", _wrap_copy_file),
        ToolSpec("move_file", "Move or rename a file", "filesystem",
                 {"source": {"type": "string", "required": True},
                  "destination": {"type": "string", "required": True}}, "judge", _wrap_move_file),
        ToolSpec("create_directory", "Create a new directory", "filesystem",
                 {"path": {"type": "string", "required": True}}, "safe", _wrap_create_directory),
        ToolSpec("diff_files", "Compare two files in the workspace and return a unified diff showing additions (+) and removals (-). Use this to review changes between file versions or compare two similar files.", "filesystem",
                 {"path_a": {"type": "string", "required": True, "description": "Relative path to the first (original) file"},
                  "path_b": {"type": "string", "required": True, "description": "Relative path to the second (new) file"}},
                 "safe", _wrap_diff_files),

        # ---- Code Analysis ----
        ToolSpec("find_function", "Find function/class definitions by name", "code_analysis",
                 {"name": {"type": "string", "required": True},
                  "path": {"type": "string", "required": False}}, "safe", _wrap_find_function),
        ToolSpec("find_todos", "Find TODO/FIXME/HACK comments in code", "code_analysis",
                 {"path": {"type": "string", "required": False}}, "safe", _wrap_find_todos),
        ToolSpec("count_lines", "Count lines of code, comments, and blanks in a file", "code_analysis",
                 {"path": {"type": "string", "required": True}}, "safe", _wrap_count_lines),
        ToolSpec("analyze_imports", "List all import statements in a file", "code_analysis",
                 {"path": {"type": "string", "required": True}}, "safe", _wrap_analyze_imports),
        ToolSpec("check_syntax", "Validate Python syntax without executing", "code_analysis",
                 {"path": {"type": "string", "required": True}}, "safe", _wrap_check_syntax),
        ToolSpec("analyze_impact", "Analyze the impact of modifying a file based on its dependencies and active editors", "code_analysis",
                 {"file_path": {"type": "string", "required": True}}, "safe", _wrap_analyze_impact),

        # ---- Web ----
        ToolSpec("web_search", "Search the web using Tavily API. Returns search result summaries with titles, URLs, and content snippets. Use for quick research, fact-checking, or finding resources. CRITICAL LIMITATIONS: (1) Results are search-engine summaries — URLs often point to aggregator/listing pages, NOT direct application or product links. If the user asks for 'exact links', 'direct links', or specific job/product URLs, you MUST follow up with browser_navigate + browser_get_all_links to extract actual destination URLs from the page. (2) ALWAYS include a 'Sources:' section at the end of your response listing URLs as markdown hyperlinks [Title](URL). (3) Use the CURRENT YEAR in search queries for recent information.", "web",
                 {"query": {"type": "string", "required": True},
                  "max_results": {"type": "number", "required": False}},
                 "safe", _wrap_web_search),
        ToolSpec("web_fetch", "Fetch a URL's content and return it as plain text (HTML is stripped, up to 5000 chars). Use when you have a specific URL and need to read its contents. LIMITATIONS: Does NOT execute JavaScript — dynamic/SPA content will be missing. For pages requiring JS rendering, login, or form interaction, use browser_navigate instead.", "web",
                 {"url": {"type": "string", "required": True}}, "safe", _wrap_web_fetch),
        ToolSpec("http_request", "Make an arbitrary HTTP request (GET, POST, PUT, PATCH, DELETE) to any URL. Returns the status code, response headers, and body. Use for testing REST APIs, triggering webhooks, or calling internal services. For public web pages, prefer web_fetch instead.", "web",
                 {"url": {"type": "string", "required": True},
                  "method": {"type": "string", "required": False, "description": "HTTP method: GET (default), POST, PUT, PATCH, DELETE"},
                  "headers": {"type": "object", "required": False, "description": "Optional request headers as key-value pairs"},
                  "body": {"type": "object", "required": False, "description": "Optional JSON request body (auto-sets Content-Type: application/json)"},
                  "timeout": {"type": "number", "required": False, "description": "Timeout in seconds (default 30)"}},
                 "judge", _wrap_http_request),

        # ---- Browser Automation ----
        ToolSpec("browser_navigate", "Navigate to a URL in a real Chromium browser with full JavaScript execution. Returns page title, status code, visible text, and iframe count. Use this INSTEAD of web_fetch when: (1) the page requires JavaScript/SPA rendering, (2) you need to interact with forms or buttons, (3) the user explicitly says 'go to browser' or 'open in browser', (4) you need to extract exact/direct links from a page. IMPORTANT: After navigating to any page with forms, IMMEDIATELY call browser_get_interactive_elements to discover selectors.", "browser",
                 {"url": {"type": "string", "required": True},
                  "wait_until": {"type": "string", "required": False}},
                 "judge", _wrap_browser_navigate),
        ToolSpec("browser_screenshot", "Capture a screenshot of the current page and stream to UI", "browser",
                 {"full_page": {"type": "boolean", "required": False}},
                 "safe", _wrap_browser_screenshot),
        ToolSpec("browser_screenshot_element", "Screenshot a specific element on the page", "browser",
                 {"selector": {"type": "string", "required": True}},
                 "safe", _wrap_browser_screenshot_element),
        ToolSpec("browser_click", "Click an element on the page by CSS selector", "browser",
                 {"selector": {"type": "string", "required": True}},
                 "judge", _wrap_browser_click),
        ToolSpec("browser_click_text", "Click an element on the page by its visible text", "browser",
                 {"text": {"type": "string", "required": True}},
                 "judge", _wrap_browser_click_text),
        ToolSpec("browser_type", "Type text into an input element. By default clears existing content first (clear_first=true). Set clear_first=false to append to existing text instead. Auto-searches iframes if selector not found on main page.", "browser",
                 {"selector": {"type": "string", "required": True, "description": "CSS selector from browser_get_interactive_elements output"},
                  "text": {"type": "string", "required": True},
                  "clear_first": {"type": "boolean", "required": False, "description": "true (default) to replace existing text, false to append"}},
                 "judge", _wrap_browser_type),
        ToolSpec("browser_press_key", "Press a keyboard key (e.g. Enter, Tab, Escape, ArrowDown)", "browser",
                 {"key": {"type": "string", "required": True}},
                 "judge", _wrap_browser_press_key),
        ToolSpec("browser_hover", "Hover over an element to trigger tooltips or menus", "browser",
                 {"selector": {"type": "string", "required": True}},
                 "safe", _wrap_browser_hover),
        ToolSpec("browser_select_option", "Select an option in a <select> dropdown", "browser",
                 {"selector": {"type": "string", "required": True},
                  "value": {"type": "string", "required": True}},
                 "judge", _wrap_browser_select_option),
        ToolSpec("browser_checkbox", "Check or uncheck a checkbox on the page", "browser",
                 {"selector": {"type": "string", "required": True},
                  "checked": {"type": "boolean", "required": True}},
                 "judge", _wrap_browser_checkbox),
        ToolSpec("browser_scroll", "Scroll the page up/down/left/right by pixels", "browser",
                 {"direction": {"type": "string", "required": True},
                  "amount": {"type": "number", "required": True},
                  "selector": {"type": "string", "required": False}},
                 "safe", _wrap_browser_scroll),
        ToolSpec("browser_scroll_to_element", "Scroll an element into view", "browser",
                 {"selector": {"type": "string", "required": True}},
                 "safe", _wrap_browser_scroll_to_element),
        ToolSpec("browser_extract_text", "Extract visible text from a page element (empty selector = whole page)", "browser",
                 {"selector": {"type": "string", "required": False}},
                 "safe", _wrap_browser_extract_text),
        ToolSpec("browser_extract_html", "Extract raw HTML from an element or the full page", "browser",
                 {"selector": {"type": "string", "required": False}},
                 "safe", _wrap_browser_extract_html),
        ToolSpec("browser_get_attribute", "Get an attribute value from an element (e.g. href, src)", "browser",
                 {"selector": {"type": "string", "required": True},
                  "attribute": {"type": "string", "required": True}},
                 "safe", _wrap_browser_get_attribute),
        ToolSpec("browser_find_elements", "Find all elements matching a CSS selector and list them", "browser",
                 {"selector": {"type": "string", "required": True},
                  "limit": {"type": "number", "required": False}},
                 "safe", _wrap_browser_find_elements),
        ToolSpec("browser_get_metadata", "Get current page URL, title, and meta description", "browser",
                 {}, "safe", _wrap_browser_get_metadata),
        ToolSpec("browser_get_all_links", "Extract all hyperlinks from the current page", "browser",
                 {"limit": {"type": "number", "required": False}},
                 "safe", _wrap_browser_get_all_links),
        ToolSpec("browser_eval_js", "Execute JavaScript in the browser and return the result", "browser",
                 {"script": {"type": "string", "required": True}},
                 "judge", _wrap_browser_eval_js),
        ToolSpec("browser_wait_for_selector", "Wait until a CSS selector appears in the DOM", "browser",
                 {"selector": {"type": "string", "required": True},
                  "timeout_ms": {"type": "number", "required": False}},
                 "safe", _wrap_browser_wait_for_selector),
        ToolSpec("browser_wait_for_navigation", "Wait for a page navigation to complete", "browser",
                 {"timeout_ms": {"type": "number", "required": False}},
                 "safe", _wrap_browser_wait_for_navigation),
        ToolSpec("browser_wait_ms", "Wait for a specified number of milliseconds (max 10s)", "browser",
                 {"ms": {"type": "number", "required": True}},
                 "safe", _wrap_browser_wait_ms),
        ToolSpec("browser_go_back", "Navigate back in browser history", "browser",
                 {}, "safe", _wrap_browser_go_back),
        ToolSpec("browser_go_forward", "Navigate forward in browser history", "browser",
                 {}, "safe", _wrap_browser_go_forward),
        ToolSpec("browser_reload", "Reload the current page", "browser",
                 {}, "safe", _wrap_browser_reload),
        ToolSpec("browser_get_url", "Get the current page URL", "browser",
                 {}, "safe", _wrap_browser_get_url),
        ToolSpec("browser_get_cookies", "Get all cookies for the current browser session", "browser",
                 {}, "safe", _wrap_browser_get_cookies),
        ToolSpec("browser_clear_cookies", "Clear all cookies for the current browser session", "browser",
                 {}, "judge", _wrap_browser_clear_cookies),
        ToolSpec("browser_open_tab", "Open a URL in a new browser tab", "browser",
                 {"url": {"type": "string", "required": True}},
                 "judge", _wrap_browser_open_tab),
        ToolSpec("browser_list_tabs", "List all open browser tabs for this agent", "browser",
                 {}, "safe", _wrap_browser_list_tabs),
        ToolSpec("browser_switch_tab", "Switch focus to a browser tab by index", "browser",
                 {"index": {"type": "number", "required": True}},
                 "judge", _wrap_browser_switch_tab),
        ToolSpec("browser_close_tab", "Close a browser tab by index", "browser",
                 {"index": {"type": "number", "required": True}},
                 "judge", _wrap_browser_close_tab),
        ToolSpec("browser_close_session", "Close and release the agent's entire browser session", "browser",
                 {}, "judge", _wrap_browser_close_session),
        ToolSpec("browser_get_interactive_elements",
                 "IMPORTANT: Call this FIRST after navigating to any page with forms. "
                 "Discovers all interactive elements (inputs, selects, buttons, textareas) on the page AND inside iframes. "
                 "Returns the exact CSS selectors to use with browser_type, browser_click, etc. NEVER guess selectors.",
                 "browser",
                 {"selector_scope": {"type": "string", "required": False,
                  "description": "Optional CSS selector to scope the search (e.g. 'form#apply'). Defaults to the whole page."}},
                 "safe", _wrap_browser_get_interactive_elements),
        ToolSpec("browser_switch_to_frame",
                 "Get info about a specific iframe by its index (from browser_get_interactive_elements output)",
                 "browser",
                 {"frame_index": {"type": "number", "required": True}},
                 "safe", _wrap_browser_switch_to_frame),

        # ---- Coordination ----
        ToolSpec("spawn_agent", "Spawn a teammate's ReACT loop with a task", "coordination",
                 {"agent_name": {"type": "string", "required": True},
                  "task": {"type": "string", "required": True}},
                 "safe", _wrap_spawn_agent),
        ToolSpec("hire_subagent", "Dynamically hire a temporary subagent to offload a specific task. CRITICAL: The subagent has ZERO context from your conversation — you MUST include ALL necessary file paths, error messages, requirements, and constraints in the 'task' parameter. Vague tasks like 'fix the login page' WILL fail.", "coordination",
                 {"role": {"type": "string", "required": True, "description": "Role name (e.g. 'coder', 'debugger', 'researcher')"},
                  "expertise": {"type": "string", "required": True, "description": "Domain expertise needed (e.g. 'React frontend', 'Python backend')"},
                  "task": {"type": "string", "required": True, "description": "FULLY SELF-CONTAINED task description with ALL context, file paths, and constraints"},
                  "model": {"type": "string", "required": False}},
                 "judge", _wrap_hire_subagent),
        ToolSpec("send_message", "Send a message in the team chat", "coordination",
                 {"text": {"type": "string", "required": True},
                  "recipient_name": {"type": "string", "required": False}},
                 "safe", _wrap_send_message),

        # ---- Tasks ----
        ToolSpec("create_task", "Create a task on the team board. NOTE: This ONLY adds the task to the UI board. To actually make an agent start working on it, you MUST follow up by using the `spawn_agent` tool or `send_message` tool.", "task",
                 {"title": {"type": "string", "required": True},
                  "description": {"type": "string", "required": False},
                  "priority": {"type": "string", "required": False},
                  "assignee": {"type": "string", "required": False},
                  "blocked_by_task_id": {"type": "string", "required": False, "description": "ID of a task that must be completed before this task can start"}},
                 "safe", _wrap_create_task),
        ToolSpec("list_tasks", "List tasks on the team board", "task",
                 {"status": {"type": "string", "required": False}},
                 "safe", _wrap_list_tasks),
        ToolSpec("update_task", "Update a task's status and/or assign it to a teammate by name", "task",
                 {"task_id": {"type": "string", "required": True},
                  "status": {"type": "string", "required": False},
                  "notes": {"type": "string", "required": False},
                  "assignee_name": {"type": "string", "required": False, "description": "Name of the agent to assign the task to"},
                  "blocked_by_task_id": {"type": "string", "required": False, "description": "ID of a task that must be completed before this task can start"}},
                 "safe", _wrap_update_task),
        ToolSpec("comment_on_task", "Add a comment to a task", "task",
                 {"task_id": {"type": "string", "required": True},
                  "text": {"type": "string", "required": True}},
                 "safe", _wrap_comment_on_task),

        # ---- Interaction ----
        ToolSpec("ask_user", "Ask the human a clarifying question and wait for their answer", "interaction",
                 {"question": {"type": "string", "required": True}},
                 "safe", _wrap_ask_user),
        ToolSpec("sleep", "Pause execution for a number of seconds", "interaction",
                 {"seconds": {"type": "number", "required": True}},
                 "safe", _wrap_sleep),
                 
        # ---- Voice & Meetings ----
        ToolSpec("join_meeting", "Join a Google Meet or Zoom call and listen to audio", "browser",
                 {"url": {"type": "string", "required": True}},
                 "judge", _wrap_join_meeting),
        ToolSpec("join_google_meet", "Join a Google Meet call and start live DOM captions", "browser",
                 {"url": {"type": "string", "required": True}},
                 "judge", _wrap_join_google_meet),
        ToolSpec("send_google_meet_chat", "Send a message to the Google Meet chat box", "browser",
                 {"text": {"type": "string", "required": True}},
                 "judge", _wrap_send_google_meet_chat),

        # ---- Memory ----
        ToolSpec("update_memory", "Update a specific long-term memory lesson in the database", "memory",
                 {"memory_id": {"type": "string", "required": True},
                  "new_lesson": {"type": "string", "required": True}},
                 "safe", _wrap_update_memory),
        ToolSpec("forget_memory", "Delete a specific long-term memory from the database", "memory",
                 {"memory_id": {"type": "string", "required": True}},
                 "safe", _wrap_forget_memory),
                 
        # ---- Google Workspace ----
        ToolSpec("create_meeting", "Create a Google Calendar event with a Meet link", "workspace",
                 {"summary": {"type": "string", "required": True},
                  "start_time_iso": {"type": "string", "required": True},
                  "end_time_iso": {"type": "string", "required": True},
                  "attendees_emails": {"type": "array", "required": False}},
                 "judge", _wrap_create_meeting),
        ToolSpec("send_email", "Send an email using Gmail", "workspace",
                 {"to_email": {"type": "string", "required": True},
                  "subject": {"type": "string", "required": True},
                  "body": {"type": "string", "required": True}},
                 "judge", _wrap_send_email),
        ToolSpec("generate_mom", "Generate structured Minutes of Meeting from a transcription", "workspace",
                 {"transcription": {"type": "string", "required": True}},
                 "safe", _wrap_generate_mom),

        # ---- Scratchpad ----
        ToolSpec("read_scratchpad", "Read your personal scratchpad or the shared team scratchpad", "memory",
                 {"target": {"type": "string", "required": False, "description": "'personal' (default) or 'team'"}},
                 "safe", _wrap_read_scratchpad),
        ToolSpec("write_scratchpad", "Append (or overwrite) notes on your personal scratchpad or the shared team scratchpad", "memory",
                 {"content": {"type": "string", "required": True},
                  "target": {"type": "string", "required": False, "description": "'personal' (default) or 'team'"},
                  "mode": {"type": "string", "required": False, "description": "'append' (default) or 'overwrite'"}},
                 "safe", _wrap_write_scratchpad),
        ToolSpec("update_scratchpad", "Replace the full contents of your personal scratchpad or the shared team scratchpad", "memory",
                 {"content": {"type": "string", "required": True},
                  "target": {"type": "string", "required": False, "description": "'personal' (default) or 'team'"}},
                 "safe", _wrap_update_scratchpad),
        ToolSpec("clear_scratchpad", "Delete/clear your personal scratchpad or the shared team scratchpad", "memory",
                 {"target": {"type": "string", "required": False, "description": "'personal' (default) or 'team'"}},
                 "safe", _wrap_clear_scratchpad),
    ]

    for spec in builtins:
        ToolRegistry.register(spec)

    logger.info("🔧 [ToolRegistry] Registered %d built-in tools.", len(builtins))


class ToolExecutor:
    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_id: str,
        agent_name: str,
        team_id: str,
        permissions: Dict[str, str],
        active_message_id: str | None = None,
        context: ToolExecutionContext | None = None,
        permission_context: ToolPermissionContext | None = None,
    ) -> str:
        """
        Gated Execution entrypoint.
        Checks tool permissions and enforces safe execution or human-in-the-loop gating.
        """
        spec = ToolRegistry.get(tool_name)
        if not spec:
            return f"Error: Tool '{tool_name}' is not registered in the system."

        # Permission level: agent-specific override → tool default
        gate_level = permissions.get(tool_name, spec.permission_default)

        # Apply granular permissions if provided
        if permission_context:
            if tool_name in permission_context.always_deny:
                logger.info("🛑 [Executor] Tool '%s' execution automatically denied by always_deny rule.", tool_name)
                return f"✗ Execution Cancelled: '{tool_name}' is explicitly denied by permission context."
            if tool_name in permission_context.always_allow:
                logger.info("✓ [Executor] Tool '%s' execution automatically allowed by always_allow rule.", tool_name)
                return await self._run_tool(spec, arguments, agent_id, agent_name, team_id, active_message_id, context)

        # 0. Documentation fast-path — writing/editing .md/.txt notes (e.g.
        # implementation.md, taskstracker.md) is always frictionless. These are
        # non-executable, workspace-sandboxed files, so we skip the Judge/human
        # gate entirely. Applies regardless of the configured gate level so the
        # user never has to approve an agent's planning notes.
        if _is_doc_write(tool_name, arguments):
            logger.info("📝 [Executor] Frictionless doc write for '%s' (tool=%s).", agent_name, tool_name)
            return await self._run_tool(spec, arguments, agent_id, agent_name, team_id, active_message_id, context)

        # 1. Safe — instant execution
        if gate_level == "safe":
            return await self._run_tool(spec, arguments, agent_id, agent_name, team_id, active_message_id, context)

        # 2. Judge — LLM-based review, then execute
        elif gate_level == "judge":
            tx_id = str(uuid.uuid4())
            topic = f"team:{team_id}"
            
            # Setup human override event
            event = asyncio.Event()
            pending_approvals[tx_id] = event
            
            try:
                # 1. Publish approval request to UI instantly
                await event_bus.publish(topic, {
                    "type": "approval_request",
                    "tx_id": tx_id,
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "text": f"⚠️ Judge AI is evaluating '{tool_name}'... (You can override now)"
                })
                
                # 2. Start concurrent Judge evaluation
                judge_task = asyncio.create_task(
                    judge_evaluator.evaluate(tool_name, arguments, agent_name, team_id=team_id)
                )
                human_task = asyncio.create_task(event.wait())
                
                logger.info("⚖️ [Executor] Racing Judge vs Human for agent '%s' tool=%s tx_id=%s", agent_name, tool_name, tx_id)
                
                # 3. Wait for the FIRST one to finish
                done, pending = await asyncio.wait(
                    [judge_task, human_task], 
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=APPROVAL_TIMEOUT_SECS
                )
                
                if not done:
                    # Both timed out
                    judge_task.cancel()
                    logger.warning("[Executor] Approval for tx_id=%s timed out after %ds.", tx_id, APPROVAL_TIMEOUT_SECS)
                    await event_bus.publish(topic, {
                        "type": "approval_resolved",
                        "tx_id": tx_id,
                        "status": "denied",
                        "reason": "Timed out waiting for approval"
                    })
                    return f"✗ Approval timed out after {APPROVAL_TIMEOUT_SECS}s: '{tool_name}' was not approved."
                
                if human_task in done:
                    # Human answered first
                    judge_task.cancel()
                    override_approved = approval_results.get(tx_id, False)
                    
                    if override_approved:
                        logger.info("✓ [Executor] tx_id=%s HUMAN APPROVED (preempted judge).", tx_id)
                        await event_bus.publish(topic, {
                            "type": "approval_resolved",
                            "tx_id": tx_id,
                            "status": "approved",
                            "reason": "Human override approved"
                        })
                        return await self._run_tool(spec, arguments, agent_id, agent_name, team_id, active_message_id, context)
                    else:
                        logger.info("✗ [Executor] tx_id=%s HUMAN DENIED (preempted judge).", tx_id)
                        await event_bus.publish(topic, {
                            "type": "approval_resolved",
                            "tx_id": tx_id,
                            "status": "denied",
                            "reason": "Human override denied"
                        })
                        return f"✗ Execution Cancelled: Human operator denied approval to run '{tool_name}'."
                
                if judge_task in done:
                    # Judge answered first
                    try:
                        approved, reason = judge_task.result()
                    except Exception as e:
                        logger.error("[Executor] Judge evaluator crashed: %s", e)
                        approved, reason = False, f"Judge crashed during evaluation: {e}"
                    if approved:
                        human_task.cancel()
                        logger.info("✓ [Executor] tx_id=%s JUDGE APPROVED.", tx_id)
                        
                        # Notify UI that approval is resolved so card can disappear
                        await event_bus.publish(topic, {
                            "type": "approval_resolved",
                            "tx_id": tx_id,
                            "status": "approved",
                            "reason": reason
                        })
                        return await self._run_tool(spec, arguments, agent_id, agent_name, team_id, active_message_id, context)
                    else:
                        # Judge denied. We DO NOT cancel human task. We wait for human override!
                        logger.info("🛑 [Executor] tx_id=%s JUDGE DENIED. Awaiting human override...", tx_id)
                        
                        # Update UI to show denial reason
                        await event_bus.publish(topic, {
                            "type": "approval_update",
                            "tx_id": tx_id,
                            "text": f"🛑 Judge DENIED execution: {reason}\nRequire human override to proceed."
                        })
                        
                        # Wait for human task (remaining time)
                        try:
                            await asyncio.wait_for(human_task, timeout=APPROVAL_TIMEOUT_SECS)
                        except asyncio.TimeoutError:
                            logger.warning("[Executor] Override for tx_id=%s timed out after %ds.", tx_id, APPROVAL_TIMEOUT_SECS)
                            await event_bus.publish(topic, {
                                "type": "approval_resolved",
                                "tx_id": tx_id,
                                "status": "denied",
                                "reason": "Timed out waiting for human override"
                            })
                            return f"✗ Approval timed out after {APPROVAL_TIMEOUT_SECS}s: '{tool_name}' was not approved."
                        
                        override_approved = approval_results.get(tx_id, False)
                        
                        if override_approved:
                            logger.info("✓ [Executor] tx_id=%s OVERRIDE APPROVED. Resuming...", tx_id)
                            await event_bus.publish(topic, {
                                "type": "approval_resolved",
                                "tx_id": tx_id,
                                "status": "approved",
                                "reason": "Human override approved"
                            })
                            return await self._run_tool(spec, arguments, agent_id, agent_name, team_id, active_message_id, context)
                        else:
                            logger.info("✗ [Executor] tx_id=%s OVERRIDE DENIED.", tx_id)
                            await event_bus.publish(topic, {
                                "type": "approval_resolved",
                                "tx_id": tx_id,
                                "status": "denied",
                                "reason": "Human override denied"
                            })
                            return f"✗ Execution Cancelled: Human operator denied approval to run '{tool_name}' after Judge rejection."
            finally:
                pending_approvals.pop(tx_id, None)
                approval_results.pop(tx_id, None)

        # 3. Human — block until user approves via POST /api/tools/approve/{tx_id}
        elif gate_level == "human":
            tx_id = str(uuid.uuid4())
            topic = f"team:{team_id}"

            event = asyncio.Event()
            pending_approvals[tx_id] = event

            try:
                await event_bus.publish(topic, {
                    "type": "approval_request",
                    "tx_id": tx_id,
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "text": f"🛑 Approval Required: Agent '{agent_name}' wants to execute '{tool_name}'."
                })

                logger.info(
                    "🛑 [Executor] Pausing agent '%s'. Awaiting human approval for tx_id=%s tool=%s",
                    agent_name, tx_id, tool_name
                )

                try:
                    await asyncio.wait_for(event.wait(), timeout=APPROVAL_TIMEOUT_SECS)
                except asyncio.TimeoutError:
                    logger.warning(
                        "[Executor] Approval for tx_id=%s timed out after %ds — denying.",
                        tx_id, APPROVAL_TIMEOUT_SECS
                    )
                    await event_bus.publish(topic, {
                        "type": "approval_resolved",
                        "tx_id": tx_id,
                        "status": "denied",
                        "reason": "Timed out waiting for approval"
                    })
                    return f"✗ Approval timed out after {APPROVAL_TIMEOUT_SECS}s: '{tool_name}' was not approved."

                approved = approval_results.get(tx_id, False)

                if approved:
                    logger.info("✓ [Executor] tx_id=%s APPROVED. Resuming execution...", tx_id)
                    await event_bus.publish(topic, {
                        "type": "approval_resolved",
                        "tx_id": tx_id,
                        "status": "approved",
                        "reason": "Human approved"
                    })
                    return await self._run_tool(spec, arguments, agent_id, agent_name, team_id, active_message_id, context)
                else:
                    logger.info("✗ [Executor] tx_id=%s DENIED. Cancelling execution...", tx_id)
                    await event_bus.publish(topic, {
                        "type": "approval_resolved",
                        "tx_id": tx_id,
                        "status": "denied",
                        "reason": "Human denied"
                    })
                    return f"✗ Execution Cancelled: Human operator denied approval to run '{tool_name}'."
            finally:
                pending_approvals.pop(tx_id, None)
                approval_results.pop(tx_id, None)

        else:
            return f"Error: Unknown tool permission gate level '{gate_level}'."

    async def _run_tool(
        self, spec: ToolSpec, arguments: Dict[str, Any],
        agent_id: str, agent_name: str, team_id: str,
        active_message_id: str | None = None,
        context: ToolExecutionContext | None = None,
    ) -> str:
        """Executes the tool handler and emits file_change events for file operations."""
        # Inject agent identity + snapshot context into args.
        # Shallow-copy first so we don't mutate the caller's dict or leak
        # internal keys into persisted tool-call records.
        arguments = {**arguments}
        arguments["_agent_id"] = agent_id
        arguments["_agent_name"] = agent_name
        arguments["_active_message_id"] = active_message_id  # used by write_file / edit_file for FileBackup
        arguments["_team_id"] = team_id
        if context:
            arguments["_context"] = context
        try:
            result = await spec.handler(arguments, team_id)
        except Exception as e:
            logger.exception("[Executor] Tool '%s' raised: %s", spec.name, e)
            return f"Error: Tool '{spec.name}' raised an exception: {type(e).__name__}: {e}"

        # If the tool returned a FileChangeResult, emit a file_change event
        if isinstance(result, FileChangeResult):
            if result.diff:
                project_id = await _team_project_id(team_id)
                event = {
                    "type": "file_change",
                    "action": result.action,
                    "path": result.path,
                    "diff": result.diff,
                    "before_content": result.before_content,
                    "after_content": result.after_content,
                    "sender_id": agent_id,
                    "sender_name": agent_name,
                    "project_id": project_id,
                }
                await event_bus.publish(f"team:{team_id}", event)
                await event_bus.publish("system:file_changes", event)
            return result.message

        # Coerce non-string results to strings so execute() honors its -> str contract.
        if not isinstance(result, str):
            result = str(result) if result is not None else ""
        return result


# ========================
# Tool Handler Functions
# ========================

async def _wrap_read_file(args: Dict[str, Any], team_id: str) -> str:
    path = args.get("relative_path") or args.get("path") or args.get("value")
    if not path:
        return "Error: Missing parameter 'relative_path'."
    project_id = await _team_project_id(team_id)
    return await file_tools.read_file(path, project_id=project_id)

async def _check_active_editor_conflicts(relative_path: str, agent_name: str) -> None:
    try:
        from core.knowledge.code_graph import code_graph
    except ImportError:
        # Code graph module not available — skip conflict detection gracefully
        return
    from core.memory.database import async_session
    from core.memory.models import Agent, Task
    from sqlalchemy import select
    import posixpath
    
    path_str = posixpath.normpath(relative_path).replace("\\", "/")
    pid = "default"
    if pid not in code_graph.active_editors:
        return
        
    graph = await code_graph.get_graph(None)
    dependent_files = list(graph.predecessors(path_str)) if graph.has_node(path_str) else []
    
    files_to_check = [path_str] + dependent_files
    conflicting_agents = set()
    for f in files_to_check:
        editors = code_graph.active_editors[pid].get(f, set())
        for ed in editors:
            if ed != agent_name:
                conflicting_agents.add(ed)
                
    if not conflicting_agents:
        return
        
    async with async_session() as db:
        curr_stmt = select(Task).join(Agent, Agent.id == Task.assigned_agent_id).where(
            Agent.name == agent_name, Task.status == "in_progress"
        )
        curr_res = await db.execute(curr_stmt)
        curr_tasks = curr_res.scalars().all()
        
        if not curr_tasks:
            raise Exception(f"Access Denied. {', '.join(conflicting_agents)} is currently actively modifying this dependent file. You must back off and wait for them to finish.")
            
        curr_task = curr_tasks[0]
        
        exempt = False
        for c_agent_name in conflicting_agents:
            c_stmt = select(Task).join(Agent, Agent.id == Task.assigned_agent_id).where(
                Agent.name == c_agent_name, Task.status == "in_progress"
            )
            c_res = await db.execute(c_stmt)
            c_tasks = c_res.scalars().all()
            for c_task in c_tasks:
                if c_task.parent_task_id == curr_task.id or curr_task.parent_task_id == c_task.id or (curr_task.parent_task_id and curr_task.parent_task_id == c_task.parent_task_id) or c_task.id == curr_task.id:
                    exempt = True
                    break
            if exempt:
                break
                
        if not exempt:
            raise Exception(f"Access Denied. {', '.join(conflicting_agents)} is currently actively modifying this dependent file. You must back off and wait for them to finish.")


async def _wrap_write_file(args: Dict[str, Any], team_id: str):
    path = args.get("relative_path") or args.get("path")
    content = args.get("content")
    agent_name = args.get("_agent_name", "Unknown")
    message_id = args.get("_active_message_id")
    if not path:
        return (
            "Error: Missing required parameter 'relative_path'. "
            "Usage: write_file(relative_path=\"path/to/file.py\", content=\"...\")"
        )
    if content is None:
        return (
            "Error: Missing required parameter 'content'. "
            "Usage: write_file(relative_path=\"path/to/file.py\", content=\"...\")"
        )
    try:
        await _check_active_editor_conflicts(path, agent_name)
    except Exception as e:
        return f"Error: {str(e)}"
    # ── Snapshot before write ────────────────────────────────────────────────
    await _snapshot_file(path, team_id, message_id, operation="write_file")
    project_id = await _team_project_id(team_id)
    return await file_tools.write_file(path, content, agent_name, project_id=project_id)

async def _wrap_edit_file(args: Dict[str, Any], team_id: str):
    path = args.get("relative_path") or args.get("path")
    target = args.get("target_content") or args.get("target")
    replacement = args.get("replacement_content") or args.get("replacement")
    agent_name = args.get("_agent_name", "Unknown")
    message_id = args.get("_active_message_id")
    if not path or target is None or replacement is None:
        return "Error: Missing parameters for editing."
    try:
        await _check_active_editor_conflicts(path, agent_name)
    except Exception as e:
        return f"Error: {str(e)}"
    # ── Snapshot before edit ─────────────────────────────────────────────────
    await _snapshot_file(path, team_id, message_id, operation="edit_file")
    project_id = await _team_project_id(team_id)
    return await file_tools.edit_file(path, target, replacement, agent_name, project_id=project_id)


async def _snapshot_file(relative_path: str, team_id: str, message_id: str | None, operation: str = "write_file"):
    """Save the current file content to FileBackup before it is modified.

    If the file does not exist (newly created), `backup_file_name` is saved as NULL.
    If `message_id` is None, the snapshot is skipped.
    """
    if not message_id:
        return
    try:
        import uuid as _uuid
        import shutil
        import hashlib
        from pathlib import Path
        from core.memory.database import async_session
        from core.memory.models import FileBackup
        from core.tools.file_tools import file_tools as _ft
        from core.config import CAROLE_HOME_DIR

        abs_path = str(_ft._resolve_safe_path(relative_path))
        p = Path(abs_path)
        
        backup_file_name = None
        if p.exists():
            path_hash = hashlib.sha256(abs_path.encode()).hexdigest()[:16]
            team_carole_dir = await _ft.get_team_carole_dir(team_id)
            history_dir = team_carole_dir / "file-history"
            history_dir.mkdir(parents=True, exist_ok=True)
            
            version = 1
            while True:
                backup_file_name = f"{path_hash}@v{version}"
                backup_path = history_dir / backup_file_name
                if not backup_path.exists():
                    break
                version += 1
                
            shutil.copy2(abs_path, backup_path)

        async with async_session() as db:
            backup = FileBackup(
                id=_uuid.uuid4(),
                team_id=_uuid.UUID(team_id) if isinstance(team_id, str) else team_id,
                message_id=_uuid.UUID(message_id) if isinstance(message_id, str) else message_id,
                file_path=abs_path,
                backup_file_name=backup_file_name,
                operation=operation,
            )
            db.add(backup)
            await db.commit()
    except Exception as e:
        logger.warning("[FileBackup] Snapshot failed for %s: %s", relative_path, e)


async def _wrap_list_directory(args: Dict[str, Any], team_id: str) -> str:
    path = args.get("relative_path", ".") or args.get("path", ".")
    project_id = await _team_project_id(team_id)
    return await file_tools.list_directory(path, project_id=project_id)

async def _team_cwd(team_id: str) -> str | None:
    """Resolve the project workspace directory for a team.

    Shell and git tools run with this as their cwd so agents operate inside
    their own project workspace rather than the shared backend root. Returns
    None on failure (callers fall back to the default workspace root).
    """
    try:
        from core.tools.file_tools import file_tools as _ft
        return str(await _ft.get_workspace_root_for_team(team_id))
    except Exception as e:
        logger.debug("workspace root resolution failed for team %s: %s", team_id, e)
        return None


_team_project_cache: dict = {}


async def _team_project_id(team_id: str) -> str | None:
    """Resolve a team_id to its project_id (cached in-process).

    File tools need the project_id to scope reads/writes to the agent's own
    project workspace. Without it they fall back to the backend root — a
    sandbox hole. Returns None only if team_id is missing/invalid.
    """
    if not team_id:
        return None
    cached = _team_project_cache.get(team_id)
    if cached is not None:
        return cached
    project_id: str | None = None
    try:
        import uuid as _uuid
        from core.memory.database import async_session
        from core.memory.models import Team
        from sqlalchemy import select
        team_uuid = _uuid.UUID(team_id)
        async with async_session() as db:
            team = (await db.execute(select(Team).where(Team.id == team_uuid))).scalar_one_or_none()
            if team:
                project_id = str(team.project_id)
    except Exception as e:
        logger.debug("project resolution failed for team %s: %s", team_id, e)
    _team_project_cache[team_id] = project_id
    return project_id


async def _wrap_execute_command(args: Dict[str, Any], team_id: str) -> str:
    command = args.get("command") or args.get("value")
    if not command:
        return "Error: Missing parameter 'command'."
    timeout = float(args.get("timeout", 60.0))
    context = args.get("_context")
    base_cwd = await _team_cwd(team_id)
    # Allow agent to specify a subdirectory relative to workspace root
    sub_cwd = args.get("cwd")
    if sub_cwd and base_cwd:
        import os
        resolved = os.path.normpath(os.path.join(base_cwd, sub_cwd))
        # Security: ensure resolved path is still within the workspace
        if resolved.startswith(base_cwd):
            cwd = resolved
        else:
            return f"Error: cwd '{sub_cwd}' escapes the workspace root."
    else:
        cwd = base_cwd
    return await shell_tools.execute_command(command, team_id, timeout, context=context, cwd=cwd)


async def _wrap_git_status(args: Dict[str, Any], team_id: str) -> str:
    return await git_tools.status(cwd=await _team_cwd(team_id))

async def _wrap_git_diff(args: Dict[str, Any], team_id: str) -> str:
    staged = args.get("staged", False)
    return await git_tools.diff(staged=staged, cwd=await _team_cwd(team_id))

async def _wrap_git_add(args: Dict[str, Any], team_id: str) -> str:
    paths = args.get("paths", ".") or args.get("value", ".")
    return await git_tools.add(paths, cwd=await _team_cwd(team_id))

async def _wrap_git_commit(args: Dict[str, Any], team_id: str) -> str:
    message = args.get("message") or args.get("value", "")
    return await git_tools.commit(message, cwd=await _team_cwd(team_id))

async def _wrap_git_log(args: Dict[str, Any], team_id: str) -> str:
    count = int(args.get("count", 10))
    return await git_tools.log(count=count, cwd=await _team_cwd(team_id))

async def _wrap_git_checkout(args: Dict[str, Any], team_id: str) -> str:
    branch = args.get("branch") or args.get("value", "")
    create = args.get("create", False)
    return await git_tools.checkout_branch(branch, create=create, cwd=await _team_cwd(team_id))

async def _wrap_git_push(args: Dict[str, Any], team_id: str) -> str:
    remote = args.get("remote", "origin")
    branch = args.get("branch")
    return await git_tools.push(remote, branch, cwd=await _team_cwd(team_id))

async def _wrap_git_pull(args: Dict[str, Any], team_id: str) -> str:
    remote = args.get("remote", "origin")
    branch = args.get("branch")
    return await git_tools.pull(remote, branch, cwd=await _team_cwd(team_id))

async def _wrap_git_branch(args: Dict[str, Any], team_id: str) -> str:
    show_all = args.get("all", False)
    return await git_tools.branch(all=show_all, cwd=await _team_cwd(team_id))

async def _wrap_web_search(args: Dict[str, Any], team_id: str) -> str:
    query = args.get("query") or args.get("value", "")
    if not query:
        return "Error: Missing parameter 'query'."
    max_results = int(args.get("max_results", 5))
    return await web_tools.web_search(query, max_results)

async def _wrap_web_fetch(args: Dict[str, Any], team_id: str) -> str:
    url = args.get("url") or args.get("value", "")
    if not url:
        return "Error: Missing parameter 'url'."
    return await web_tools.web_fetch(url)

async def _wrap_http_request(args: Dict[str, Any], team_id: str) -> str:
    url = args.get("url") or args.get("value", "")
    if not url:
        return "Error: Missing parameter 'url'."
    method = args.get("method", "GET")
    headers = args.get("headers")
    body = args.get("body")
    timeout = float(args.get("timeout", 30.0))
    return await web_tools.http_request(url, method=method, headers=headers, body=body, timeout=timeout)

async def _wrap_diff_files(args: Dict[str, Any], team_id: str) -> str:
    path_a = args.get("path_a") or args.get("file_a", "")
    path_b = args.get("path_b") or args.get("file_b", "")
    if not path_a or not path_b:
        return "Error: Both 'path_a' and 'path_b' are required."
    project_id = await _team_project_id(team_id)
    return await file_tools.diff_files(path_a, path_b, team_id=team_id, project_id=project_id)

# ---- Browser Wrappers ----
# These wrappers need agent identity context, which the standard (args, team_id)
# signature doesn't provide. We store it in the args dict from the ToolExecutor.

# ===========================================================
# Browser Automation Wrappers
# ===========================================================

async def _wrap_browser_navigate(args: Dict[str, Any], team_id: str) -> str:
    url = args.get("url") or args.get("value", "")
    if not url:
        return "Error: Missing parameter 'url'."
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    wait_until = args.get("wait_until", "domcontentloaded")
    return await browser_tool.navigate(url, agent_id, agent_name, team_id, wait_until=wait_until)

async def _wrap_browser_screenshot(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    full_page = bool(args.get("full_page", False))
    return await browser_tool.screenshot(agent_id, agent_name, team_id, full_page=full_page)

async def _wrap_browser_screenshot_element(args: Dict[str, Any], team_id: str) -> str:
    selector = args.get("selector", "")
    if not selector:
        return "Error: Missing parameter 'selector'."
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    return await browser_tool.screenshot_element(selector, agent_id, agent_name, team_id)

async def _wrap_browser_click(args: Dict[str, Any], team_id: str) -> str:
    selector = args.get("selector", "")
    if not selector:
        return "Error: Missing parameter 'selector'."
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    return await browser_tool.click(selector, agent_id, agent_name=agent_name, team_id=team_id)

async def _wrap_browser_click_text(args: Dict[str, Any], team_id: str) -> str:
    text = args.get("text", "")
    if not text:
        return "Error: Missing parameter 'text'."
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    return await browser_tool.click_text(text, agent_id, agent_name=agent_name, team_id=team_id)

async def _wrap_browser_type(args: Dict[str, Any], team_id: str) -> str:
    selector = args.get("selector", "")
    text = args.get("text", "")
    if not selector or not text:
        return "Error: Missing 'selector' or 'text'."
    agent_id = args.get("_agent_id", "unknown")
    clear_first = bool(args.get("clear_first", True))
    return await browser_tool.type_text(selector, text, agent_id, clear_first=clear_first)

async def _wrap_browser_press_key(args: Dict[str, Any], team_id: str) -> str:
    key = args.get("key", "")
    if not key:
        return "Error: Missing parameter 'key'."
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.press_key(key, agent_id)

async def _wrap_browser_hover(args: Dict[str, Any], team_id: str) -> str:
    selector = args.get("selector", "")
    if not selector:
        return "Error: Missing parameter 'selector'."
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    return await browser_tool.hover(selector, agent_id, agent_name=agent_name, team_id=team_id)

async def _wrap_browser_select_option(args: Dict[str, Any], team_id: str) -> str:
    selector = args.get("selector", "")
    value = args.get("value", "")
    if not selector or not value:
        return "Error: Missing 'selector' or 'value'."
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.select_option(selector, value, agent_id)

async def _wrap_browser_checkbox(args: Dict[str, Any], team_id: str) -> str:
    selector = args.get("selector", "")
    checked = args.get("checked", True)
    if not selector:
        return "Error: Missing parameter 'selector'."
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.check_checkbox(selector, bool(checked), agent_id)

async def _wrap_browser_scroll(args: Dict[str, Any], team_id: str) -> str:
    direction = args.get("direction", "down")
    amount = int(args.get("amount", 300))
    selector = args.get("selector", "")
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.scroll(direction, amount, agent_id, selector=selector)

async def _wrap_browser_scroll_to_element(args: Dict[str, Any], team_id: str) -> str:
    selector = args.get("selector", "")
    if not selector:
        return "Error: Missing parameter 'selector'."
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.scroll_to_element(selector, agent_id)

async def _wrap_browser_extract_text(args: Dict[str, Any], team_id: str) -> str:
    selector = args.get("selector", "")
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.extract_text(selector, agent_id)

async def _wrap_browser_extract_html(args: Dict[str, Any], team_id: str) -> str:
    selector = args.get("selector", "")
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.extract_html(selector, agent_id)

async def _wrap_browser_get_attribute(args: Dict[str, Any], team_id: str) -> str:
    selector = args.get("selector", "")
    attribute = args.get("attribute", "")
    if not selector or not attribute:
        return "Error: Missing 'selector' or 'attribute'."
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.get_attribute(selector, attribute, agent_id)

async def _wrap_browser_find_elements(args: Dict[str, Any], team_id: str) -> str:
    selector = args.get("selector", "")
    if not selector:
        return "Error: Missing parameter 'selector'."
    agent_id = args.get("_agent_id", "unknown")
    limit = int(args.get("limit", 20))
    return await browser_tool.find_elements(selector, agent_id, limit=limit)

async def _wrap_browser_get_metadata(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.get_page_metadata(agent_id)

async def _wrap_browser_get_all_links(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    limit = int(args.get("limit", 30))
    return await browser_tool.get_all_links(agent_id, limit=limit)

async def _wrap_browser_eval_js(args: Dict[str, Any], team_id: str) -> str:
    script = args.get("script", "")
    if not script:
        return "Error: Missing parameter 'script'."
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.evaluate_js(script, agent_id)

async def _wrap_browser_wait_for_selector(args: Dict[str, Any], team_id: str) -> str:
    selector = args.get("selector", "")
    if not selector:
        return "Error: Missing parameter 'selector'."
    agent_id = args.get("_agent_id", "unknown")
    timeout_ms = int(args.get("timeout_ms", 10000))
    return await browser_tool.wait_for_selector(selector, agent_id, timeout_ms=timeout_ms)

async def _wrap_browser_wait_for_navigation(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    timeout_ms = int(args.get("timeout_ms", 10000))
    return await browser_tool.wait_for_navigation(agent_id, timeout_ms=timeout_ms)

async def _wrap_browser_wait_ms(args: Dict[str, Any], team_id: str) -> str:
    ms = int(args.get("ms", 1000))
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.wait_ms(ms, agent_id)

async def _wrap_browser_go_back(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    return await browser_tool.go_back(agent_id, agent_name, team_id)

async def _wrap_browser_go_forward(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    return await browser_tool.go_forward(agent_id, agent_name, team_id)

async def _wrap_browser_reload(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    return await browser_tool.reload(agent_id, agent_name, team_id)

async def _wrap_browser_get_url(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.get_current_url(agent_id)

async def _wrap_browser_get_cookies(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.get_cookies(agent_id)

async def _wrap_browser_clear_cookies(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.clear_cookies(agent_id)

async def _wrap_browser_open_tab(args: Dict[str, Any], team_id: str) -> str:
    url = args.get("url", "")
    if not url:
        return "Error: Missing parameter 'url'."
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    return await browser_tool.open_new_tab(url, agent_id, agent_name, team_id)

async def _wrap_browser_list_tabs(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.list_tabs(agent_id)

async def _wrap_browser_switch_tab(args: Dict[str, Any], team_id: str) -> str:
    index = int(args.get("index", 0))
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    return await browser_tool.switch_tab(index, agent_id, agent_name, team_id)

async def _wrap_browser_close_tab(args: Dict[str, Any], team_id: str) -> str:
    index = int(args.get("index", 0))
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.close_tab(index, agent_id)

async def _wrap_browser_close_session(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.close_browser(agent_id)

async def _wrap_browser_get_interactive_elements(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    selector_scope = args.get("selector_scope", "")
    return await browser_tool.get_interactive_elements(agent_id, selector_scope=selector_scope)

async def _wrap_browser_switch_to_frame(args: Dict[str, Any], team_id: str) -> str:
    frame_index = int(args.get("frame_index", 0))
    agent_id = args.get("_agent_id", "unknown")
    return await browser_tool.switch_to_frame(frame_index, agent_id)


async def _wrap_spawn_agent(args: Dict[str, Any], team_id: str) -> str:
    name = args.get("agent_name") or args.get("name") or args.get("value", "")
    task = args.get("task") or args.get("prompt", "")
    if not name or not task:
        return "Error: Missing 'agent_name' or 'task'."
    parent_id = args.get("_agent_id")
    return await agent_tools.spawn_agent(name, task, team_id, parent_coordinator_id=parent_id)

async def _wrap_hire_subagent(args: Dict[str, Any], team_id: str) -> str:
    agent_name = args.get("_agent_name", "")
    # Enforce 1-Level Only Guardrail (check new prefix format too)
    if agent_name.startswith("Subagent-") or agent_name.startswith("Sub-"):
        return "Error: Subagents are not permitted to hire further subagents (Maximum depth of 1 reached)."
    
    role = args.get("role", "")
    expertise = args.get("expertise", "")
    task = args.get("task", "")
    model = args.get("model")
    
    if not role or not expertise or not task:
        return "Error: Missing 'role', 'expertise', or 'task'."
        
    agent_id = args.get("_agent_id", "")
    return await agent_tools.hire_subagent(role, expertise, task, team_id, agent_id, model=model)

async def _wrap_send_message(args: Dict[str, Any], team_id: str) -> str:
    text = args.get("text") or args.get("message") or args.get("value", "")
    sender = args.get("_agent_id", "agent")
    recipient = args.get("recipient_name")
    if not text:
        return "Error: Missing 'text'."
    return await agent_tools.send_message(text, sender, team_id, recipient)

async def _wrap_create_task(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.task_tools import task_tools
    title = args.get("title", "")
    description = args.get("description", "")
    priority = args.get("priority", "medium")
    assignee = args.get("assignee")
    blocked_by_task_id = args.get("blocked_by_task_id")
    if not title:
        return "Error: Missing 'title'."
    return await task_tools.create_task(team_id, title, description, priority, assignee, blocked_by_task_id)

async def _wrap_list_tasks(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.task_tools import task_tools
    status = args.get("status")
    return await task_tools.list_tasks(team_id, status)

async def _wrap_update_task(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.task_tools import task_tools
    task_id = args.get("task_id", "")
    status = args.get("status")
    notes = args.get("notes")
    assignee_name = args.get("assignee_name")
    blocked_by_task_id = args.get("blocked_by_task_id")
    agent_name = args.get("_agent_name")
    if not task_id:
        return "Error: Missing 'task_id'."
    return await task_tools.update_task(task_id, status, notes, assignee_name, agent_name, blocked_by_task_id)

async def _wrap_comment_on_task(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.task_tools import task_tools
    task_id = args.get("task_id", "")
    text = args.get("text", "")
    if not task_id or not text:
        return "Error: Missing 'task_id' or 'text'."
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    return await task_tools.comment_on_task(task_id, text, agent_id, agent_name)


# ---- Scratchpad Wrappers ----

async def _wrap_read_scratchpad(args: Dict[str, Any], team_id: str) -> str:
    """Read the agent's personal scratchpad or the shared team scratchpad."""
    from core.memory.scratchpad import scratchpad_store
    # 'target' may arrive via the 'value' fallback key if arg parsing degraded
    target = args.get("target") or args.get("value", "personal")
    if target not in ("personal", "team"):
        target = "personal"
    agent_name = args.get("_agent_name", "agent")
    result = await scratchpad_store.read(team_id, target, agent_name)
    content = result.get("content", "")
    label = result.get("label", "Scratchpad")
    return f"=== {label} ===\n{content}" if content.strip() else f"{label} is empty."


async def _wrap_write_scratchpad(args: Dict[str, Any], team_id: str) -> str:
    """Append (or overwrite) the agent's personal scratchpad or the shared team scratchpad."""
    from core.memory.scratchpad import scratchpad_store
    target = args.get("target", "personal")
    content = args.get("content")
    mode = args.get("mode", "append")  # 'append' or 'overwrite'
    agent_name = args.get("_agent_name", "agent")
    agent_id = args.get("_agent_id", "unknown")
    if content is None:
        return (
            "Error: Missing required parameter 'content'. "
            "Usage: write_scratchpad(content=\"your text here\", target='team')"
        )
    result = await scratchpad_store.write(team_id, target, agent_name, content, mode=mode, agent_id=agent_id)
    if result.get("status") == "error":
        return f"Error: {result.get('error')}"
    return f"✓ Written to {result.get('label')}."


async def _wrap_update_scratchpad(args: Dict[str, Any], team_id: str) -> str:
    """Replace the full contents of the agent's personal or shared team scratchpad."""
    from core.memory.scratchpad import scratchpad_store
    target = args.get("target", "personal")
    content = args.get("content")
    agent_name = args.get("_agent_name", "agent")
    agent_id = args.get("_agent_id", "unknown")
    if content is None:
        return (
            "Error: Missing required parameter 'content'. "
            "Usage: update_scratchpad(content=\"your text here\", target='team')"
        )
    result = await scratchpad_store.update(team_id, target, agent_name, content, agent_id=agent_id)
    if result.get("status") == "error":
        return f"Error: {result.get('error')}"
    return f"✓ Updated {result.get('label')}."


async def _wrap_clear_scratchpad(args: Dict[str, Any], team_id: str) -> str:
    """Delete/clear the agent's personal or shared team scratchpad."""
    from core.memory.scratchpad import scratchpad_store
    target = args.get("target") or args.get("value", "personal")
    if target not in ("personal", "team"):
        target = "personal"
    agent_name = args.get("_agent_name", "agent")
    agent_id = args.get("_agent_id", "unknown")
    result = await scratchpad_store.delete(team_id, target, agent_name, agent_id=agent_id)
    if result.get("status") == "error":
        return f"Error: {result.get('error')}"
    return f"✓ Cleared {result.get('label')}."


async def _wrap_ask_user(args: Dict[str, Any], team_id: str) -> str:
    question = args.get("question") or args.get("value", "")
    if not question:
        return "Error: Missing 'question'."
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    return await interaction_tools.ask_user(question, agent_id, agent_name, team_id)


async def _wrap_sleep(args: Dict[str, Any], team_id: str) -> str:
    seconds = float(args.get("seconds", args.get("value", 5)))
    return await interaction_tools.sleep(seconds)


# ---- Voice & Meetings Wrappers ----

async def _wrap_join_meeting(args: Dict[str, Any], team_id: str) -> str:
    url = args.get("url", "")
    if not url:
        return "Error: Missing parameter 'url'."
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    return await meeting_tool.join_meeting(url, agent_id, agent_name, team_id)

async def _wrap_join_google_meet(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.google_meet_tool import google_meet_tool
    url = args.get("url", "")
    if not url:
        return "Error: Missing parameter 'url'."
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    return await google_meet_tool.join_google_meet(url, agent_id, agent_name, team_id)

async def _wrap_send_google_meet_chat(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.google_meet_tool import google_meet_tool
    text = args.get("text", "")
    if not text:
        return "Error: Missing parameter 'text'."
    agent_id = args.get("_agent_id", "unknown")
    return await google_meet_tool.send_google_meet_chat(text, agent_id)

# ---- New Filesystem Tools ----

async def _wrap_append_file(args: Dict[str, Any], team_id: str):
    path = args.get("relative_path") or args.get("path")
    content = args.get("content")
    agent_name = args.get("_agent_name", "Unknown")
    if not path or content is None:
        return "Error: Missing 'relative_path' or 'content'."
    project_id = await _team_project_id(team_id)
    return await file_tools.append_file(path, content, agent_name, project_id=project_id)


async def _wrap_delete_file(args: Dict[str, Any], team_id: str) -> str:
    path = args.get("relative_path") or args.get("path") or args.get("value")
    agent_name = args.get("_agent_name", "Unknown")
    if not path:
        return "Error: Missing 'relative_path'."
    project_id = await _team_project_id(team_id)
    return await file_tools.delete_file(path, agent_name, project_id=project_id)


async def _wrap_grep_search(args: Dict[str, Any], team_id: str) -> str:
    pattern = args.get("pattern") or args.get("value", "")
    if not pattern:
        return "Error: Missing 'pattern'."
    path = args.get("path", ".")
    case_sensitive = args.get("case_sensitive", True)
    project_id = await _team_project_id(team_id)
    return await file_tools.grep_search(pattern, path, case_sensitive, project_id=project_id)


async def _wrap_glob_search(args: Dict[str, Any], team_id: str) -> str:
    pattern = args.get("pattern") or args.get("value", "")
    if not pattern:
        return "Error: Missing 'pattern'."
    path = args.get("path", ".")
    project_id = await _team_project_id(team_id)
    return await file_tools.glob_search(pattern, path, project_id=project_id)


# Singleton global executor
tool_executor = ToolExecutor()


# ---- New Filesystem Wrappers ----

async def _wrap_copy_file(args: Dict[str, Any], team_id: str) -> str:
    src = args.get("source", "")
    dst = args.get("destination", "")
    if not src or not dst:
        return "Error: Missing 'source' or 'destination'."
    project_id = await _team_project_id(team_id)
    return await file_tools.copy_file(src, dst, project_id=project_id)

async def _wrap_move_file(args: Dict[str, Any], team_id: str) -> str:
    src = args.get("source", "")
    dst = args.get("destination", "")
    if not src or not dst:
        return "Error: Missing 'source' or 'destination'."
    project_id = await _team_project_id(team_id)
    return await file_tools.move_file(src, dst, project_id=project_id)

async def _wrap_create_directory(args: Dict[str, Any], team_id: str) -> str:
    path = args.get("path") or args.get("relative_path") or args.get("value", "")
    if not path:
        return (
            "Error: Missing required parameter 'path'. "
            "Usage: create_directory(path=\"my_new_folder\")"
        )
    project_id = await _team_project_id(team_id)
    return await file_tools.create_directory(path, project_id=project_id)


# ---- Git Extras ----

async def _wrap_git_stash(args: Dict[str, Any], team_id: str) -> str:
    action = args.get("action", "push")
    message = args.get("message")
    return await git_tools.stash(action, message, cwd=await _team_cwd(team_id))

async def _wrap_git_clone(args: Dict[str, Any], team_id: str) -> str:
    url = args.get("url", "")
    if not url:
        return "Error: Missing 'url'."
    directory = args.get("directory")
    return await git_tools.clone(url, directory, cwd=await _team_cwd(team_id))


# ---- Code Analysis Wrappers ----

async def _wrap_find_function(args: Dict[str, Any], team_id: str) -> str:
    name = args.get("name") or args.get("value", "")
    if not name:
        return "Error: Missing 'name'."
    path = args.get("path", ".")
    return code_analysis_tools.find_function(name, path)

async def _wrap_find_todos(args: Dict[str, Any], team_id: str) -> str:
    path = args.get("path", ".")
    return code_analysis_tools.find_todos(path)

async def _wrap_count_lines(args: Dict[str, Any], team_id: str) -> str:
    path = args.get("path") or args.get("value", "")
    if not path:
        return "Error: Missing 'path'."
    return code_analysis_tools.count_lines(path)

async def _wrap_analyze_imports(args: Dict[str, Any], team_id: str) -> str:
    path = args.get("path") or args.get("value", "")
    if not path:
        return "Error: Missing 'path'."
    return code_analysis_tools.analyze_imports(path)

async def _wrap_check_syntax(args: Dict[str, Any], team_id: str) -> str:
    path = args.get("path") or args.get("value", "")
    if not path:
        return "Error: Missing 'path'."
    return code_analysis_tools.check_syntax(path)

async def _wrap_analyze_impact(args: Dict[str, Any], team_id: str) -> str:
    path = args.get("file_path") or args.get("path") or args.get("value", "")
    if not path:
        return "Error: Missing 'file_path'."
    project_id = await _team_project_id(team_id)
    return await code_analysis_tools.analyze_impact(path, project_id)

# ---- Memory Wrappers ----

async def _wrap_update_memory(args: Dict[str, Any], team_id: str) -> str:
    memory_id = args.get("memory_id", "")
    new_lesson = args.get("new_lesson", "")
    if not memory_id or not new_lesson:
        return "Error: Missing 'memory_id' or 'new_lesson'."
    return await memory_tools.update_memory(memory_id, new_lesson)

async def _wrap_forget_memory(args: Dict[str, Any], team_id: str) -> str:
    memory_id = args.get("memory_id", "")
    if not memory_id:
        return "Error: Missing 'memory_id'."
    return await memory_tools.forget_memory(memory_id)

# ---- Google Workspace Wrappers ----

async def _wrap_create_meeting(args: Dict[str, Any], team_id: str) -> str:
    summary = args.get("summary", "")
    start_time_iso = args.get("start_time_iso", "")
    end_time_iso = args.get("end_time_iso", "")
    attendees_emails = args.get("attendees_emails", [])
    if not summary or not start_time_iso or not end_time_iso:
        return "Error: Missing 'summary', 'start_time_iso', or 'end_time_iso'."
    # create_meeting is a sync function (not a coroutine), so no await is needed.
    return create_meeting(summary, start_time_iso, end_time_iso, attendees_emails)

async def _wrap_send_email(args: Dict[str, Any], team_id: str) -> str:
    to_email = args.get("to_email", "")
    subject = args.get("subject", "")
    body = args.get("body", "")
    if not to_email or not subject or not body:
        return "Error: Missing 'to_email', 'subject', or 'body'."
    # send_email is a sync function (not a coroutine), so no await is needed.
    return send_email(to_email, subject, body)

async def _wrap_generate_mom(args: Dict[str, Any], team_id: str) -> str:
    transcription = args.get("transcription", "")
    if not transcription:
        return "Error: Missing 'transcription'."
    return await meeting_tool.generate_mom(transcription)

