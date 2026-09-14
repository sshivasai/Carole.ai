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

import re
import time
import uuid
import asyncio
import logging
import os
from typing import Dict, Any

from core.chat.event_bus import event_bus
from core.tools.tool_registry import ToolRegistry, ToolSpec
from core.tools.file_tools import file_tools, FileChangeResult
from core.tools.shell_tools import shell_tools
from core.tools.git_tools import git_tools
from core.tools.web_tools import web_tools
from core.tools.agent_tools import agent_tools, _running_subagent_tasks
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


async def _publish_approval(topic: str, payload: dict):
    await event_bus.publish(topic, payload)
    team_id = topic.split(":")[-1] if ":" in topic else ""
    await _persist_approval_event(team_id, payload.get("agent_id", ""), payload.get("agent_name", ""), payload)

async def _persist_approval_event(team_id: str, agent_id: str, agent_name: str, payload: dict):
    from core.memory.database import async_session
    from core.memory.models import Message
    
    try:
        async with async_session() as db:
            msg = Message(
                team_id=uuid.UUID(team_id) if isinstance(team_id, str) else team_id,
                sender_id="system",
                sender_name="System",
                text=f"Approval Event: {payload.get('type')}",
                is_intermediate=True,
                attachments=[{"type": payload.get("type"), "payload": payload}]
            )
            db.add(msg)
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to persist approval event: {e}")

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
resolved_approvals: Dict[str, dict] = {}  # Maps tx_id to { "tx_id", "status", "action", "resolved_at" } for idempotency
pending_approval_details: Dict[str, dict] = {}  # Maps tx_id to metadata dict for inspection

# Idempotency guard — ensures register_builtin_tools() is a no-op if called twice
_builtins_registered: bool = False


def register_builtin_tools():
    """Registers all built-in tools with the ToolRegistry at startup.
    Called once from main.py lifespan."""
    global _builtins_registered
    if _builtins_registered:
        logger.debug("[ToolRegistry] Built-in tools already registered — skipping.")
        return

    builtins = [
        ToolSpec("read_skill", "Load the complete instructions for a relevant skill listed in the skills catalog.", "filesystem",
                 {"name": {"type": "string", "required": True}}, "safe", _wrap_read_skill),
        ToolSpec("read_observation", "Retrieve a range of a full cached tool result by its artifact_id.", "filesystem",
                 {"artifact_id": {"type": "string", "required": True}, "offset": {"type": "integer"},
                  "limit": {"type": "integer", "description": "Maximum characters, from 1 to 2500"}}, "safe", _wrap_read_observation),
        # ---- Filesystem (Strict Verification Pattern) ----
        ToolSpec("read_file", "Reads a file from the workspace. You MUST call this before edit_file. Returns full file content or an unchanged stub if already read in this conversation.", "filesystem",
                 {"relative_path": {"type": "string", "required": True, "description": "Path to file relative to workspace root"},
                  "force": {"type": "boolean", "required": False, "description": "Re-read content even if unchanged (default true)"},
                  "start_line": {"type": "integer", "required": False, "description": "First line, inclusive, numbered from 1"},
                  "end_line": {"type": "integer", "required": False, "description": "Last line, inclusive"}},
                 "safe", _wrap_read_file),
        ToolSpec("write_file", "Create a new file or completely overwrite an existing one. WARNING: Replaces ENTIRE file. To modify existing code, use edit_file instead.", "filesystem",
                 {"relative_path": {"type": "string", "required": True, "description": "Path to file relative to workspace root"},
                  "content": {"type": "string", "required": True, "description": "Full file content to write"}},
                 "judge", _wrap_write_file),
        ToolSpec("edit_file", "Performs exact string replacements in files. STRICT RULES: (1) You MUST call read_file first before editing, (2) target_content must match EXACTLY character-for-character including indentation, (3) target_content must be uniquely identifying (usually 2-4 lines of context). Errors if multiple matches found.", "filesystem",
                 {"relative_path": {"type": "string", "required": True, "description": "Path to file relative to workspace root"},
                  "target_content": {"type": "string", "required": True, "description": "The exact text block currently in the file that you want to replace. Must match character-for-character."},
                  "replacement_content": {"type": "string", "required": True, "description": "The new text to replace target_content with."}},
                 "judge", _wrap_edit_file),
        ToolSpec("list_directory", "List files and directories at a path. Prefer glob_search or grep_search for locating specific files.", "filesystem",
                 {"relative_path": {"type": "string", "required": False, "description": "Subdirectory to list (default: root)"}},
                 "safe", _wrap_list_directory),
        ToolSpec("append_file", "Append content to the end of an existing file.", "filesystem",
                 {"relative_path": {"type": "string", "required": True, "description": "Path to file relative to workspace root"},
                  "content": {"type": "string", "required": True, "description": "Text content to append"}},
                 "judge", _wrap_append_file),
        ToolSpec("delete_file", "Delete a file from the workspace. Requires human approval.", "filesystem",
                 {"relative_path": {"type": "string", "required": True, "description": "Path to file relative to workspace root"}},
                 "human", _wrap_delete_file),
        ToolSpec("grep_search", "Search file contents for a regex pattern. Preferred over shell grep/find.", "search",
                 {"pattern": {"type": "string", "required": True, "description": "Regex or string pattern to search for"},
                  "path": {"type": "string", "required": False, "description": "Subdirectory or file to search within"},
                  "case_sensitive": {"type": "boolean", "required": False, "description": "Whether search is case-sensitive"}},
                 "safe", _wrap_grep_search),
        ToolSpec("glob_search", "Find files matching a glob pattern (e.g. **/*.py, src/**/*.tsx). Preferred over shell ls/find.", "search",
                 {"pattern": {"type": "string", "required": True, "description": "Glob pattern to match files against"},
                  "path": {"type": "string", "required": False, "description": "Base directory for search"}},
                 "safe", _wrap_glob_search),

        # ---- Shell (Strict Exclusivity) ----
        ToolSpec("execute_command", "Execute a shell command in the workspace. Reserved for test runners (pytest/npm test), build tools, and scripts. STRICT POLICY: Do NOT use to read files (use read_file), edit files (use edit_file), create files (use write_file), or search (use grep_search). Use 'cwd' to run in subdirectories. Use 'background: true' for long-running processes or servers.", "shell",
                 {"command": {"type": "string", "required": True, "description": "Shell command to run (e.g., pytest, npm test, python main.py)"},
                  "timeout": {"type": "number", "required": False, "description": "Max seconds to wait (default 60)"},
                  "background": {"type": "boolean", "required": False, "description": "Run in background and return PID immediately (ideal for dev servers, pip install, or background workers)"},
                  "cwd": {"type": "string", "required": False, "description": "Subdirectory to run the command in, relative to workspace root (e.g. 'frontend', 'backend')"}},
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
        ToolSpec("copy_file", "Copy a file or directory into or within the workspace. Source can be a workspace-relative path or an absolute external path on disk (e.g. to copy an external project or file into the current workspace for editing). Destination must be within the project workspace.", "filesystem",
                 {"source": {"type": "string", "required": True, "description": "Source file or directory path (relative or absolute)"},
                  "destination": {"type": "string", "required": True, "description": "Destination file or directory path relative to workspace root"}}, "judge", _wrap_copy_file),
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
        ToolSpec("find_symbol_definition", "Find exact AST definition (functions, classes, interfaces) with code snippets and line numbers without reading whole files", "code_analysis",
                 {"symbol_name": {"type": "string", "required": True}}, "safe", _wrap_find_symbol_definition),
        ToolSpec("get_file_outline", "Get structural outline (classes, methods, functions) of a source file with line numbers", "code_analysis",
                 {"file_path": {"type": "string", "required": True}}, "safe", _wrap_get_file_outline),
        ToolSpec("get_symbol_callers", "Find all functions and files that invoke a symbol across the workspace", "code_analysis",
                 {"symbol_name": {"type": "string", "required": True}}, "safe", _wrap_get_symbol_callers),
        ToolSpec("get_symbol_callees", "Find all functions called inside a specific function/class", "code_analysis",
                 {"function_name": {"type": "string", "required": True},
                  "file_path": {"type": "string", "required": True}}, "safe", _wrap_get_symbol_callees),
        ToolSpec("find_definitions", "Jump straight to the AST definition of a type, class, or function across the workspace", "code_analysis",
                 {"symbol": {"type": "string", "required": True}}, "safe", _wrap_find_definitions),
        ToolSpec("find_callers", "Retrieve all call sites and references for a symbol before refactoring", "code_analysis",
                 {"function_name": {"type": "string", "required": True}}, "safe", _wrap_find_callers),
        ToolSpec("get_module_dependencies", "Inspect import/export dependency graph for a specific module", "code_analysis",
                 {"file_path": {"type": "string", "required": True}}, "safe", _wrap_get_module_dependencies),
        ToolSpec("hybrid_code_search", "Dual BM25 and vector code retrieval fused via Reciprocal Rank Fusion", "code_analysis",
                 {"query": {"type": "string", "required": True},
                  "top_k": {"type": "number", "required": False},
                  "file_filter": {"type": "string", "required": False},
                  "kind": {"type": "string", "required": False}}, "safe", _wrap_hybrid_code_search),
        ToolSpec("get_class_hierarchy", "Inspect superclasses, subclasses, and inheritance tree for a class", "code_analysis",
                 {"class_name": {"type": "string", "required": True}}, "safe", _wrap_get_class_hierarchy),

        # ---- Web ----
        ToolSpec("web_search", "Search the web using Tavily API. Returns search result summaries with titles, URLs, and content snippets. Use for quick research, fact-checking, or finding resources. If direct links from a known static page are needed, prefer web_extract_links before launching a full browser. ALWAYS include a 'Sources:' section at the end of your response listing URLs as markdown hyperlinks [Title](URL).", "web",
                 {"query": {"type": "string", "required": True},
                  "max_results": {"type": "integer", "required": False}},
                 "safe", _wrap_web_search),
        ToolSpec("web_fetch", "Fetch static public web content. Text is returned in markdown and limited to 20,000 characters. Known document/image formats return managed file metadata. Does not execute JavaScript.", "web",
                 {"url": {"type": "string", "required": True}}, "safe", _wrap_web_fetch),
        ToolSpec("web_extract_links", "Extract direct HTTP(S) links from a public static HTML page. Returns link text and absolute URLs without launching a browser. Does not execute JavaScript or verify each destination.", "web",
                 {"url": {"type": "string", "required": True, "description": "Public HTML page URL"},
                  "limit": {"type": "integer", "required": False, "minimum": 1, "maximum": 200, "description": "Maximum links to return; default 50"}},
                 "safe", _wrap_web_extract_links),
        ToolSpec("http_request", "Make a public HTTP request (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS). No automatic redirects or private-network access. Response headers and text output are bounded.", "web",
                 {"url": {"type": "string", "required": True},
                  "method": {"type": "string", "required": False, "description": "HTTP method: GET (default), POST, PUT, PATCH, DELETE, HEAD, OPTIONS"},
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
        ToolSpec("browser_snapshot",
                 "PRIMARY TOOL for understanding a web page. Renders the live DOM as a compact Accessibility Tree "
                 "where every interactive element (button, input, link, select) is assigned a numbered Ref like [12]. "
                 "Call this AFTER browser_navigate and AFTER any browser_act that changes the page. "
                 "Then use browser_act(kind='click', ref=12) to interact. NEVER guess CSS selectors.",
                 "browser",
                 {"include_screenshot": {"type": "boolean", "required": False,
                  "description": "Whether to stream a screenshot alongside the snapshot (default: true)."}},
                 "safe", _wrap_browser_snapshot),
        ToolSpec("browser_act",
                 "Unified browser action dispatcher. Interact with elements by Ref number from browser_snapshot. "
                 "kind options: click (ref or selector), type (ref or selector + text), clear, hover, select (+ value), "
                 "check, uncheck, press (key), scroll_down, scroll_up, coords (x+y). "
                 "After any act that navigates the page, call browser_snapshot to get fresh refs.",
                 "browser",
                 {"kind": {"type": "string", "required": True,
                   "description": "Action kind: click|type|clear|hover|select|check|uncheck|press|scroll_down|scroll_up|coords"},
                  "ref": {"type": "number", "required": False,
                   "description": "Ref number from browser_snapshot (preferred over selector)"},
                  "selector": {"type": "string", "required": False,
                   "description": "CSS selector fallback if no ref available"},
                  "text": {"type": "string", "required": False,
                   "description": "Text to type (for kind=type)"},
                  "key": {"type": "string", "required": False,
                   "description": "Key to press, e.g. Enter, Tab, Escape (for kind=press)"},
                  "value": {"type": "string", "required": False,
                   "description": "Value or label to select (for kind=select)"},
                  "x": {"type": "number", "required": False,
                   "description": "X coordinate (for kind=coords)"},
                  "y": {"type": "number", "required": False,
                   "description": "Y coordinate (for kind=coords)"},
                  "frame_index": {"type": "number", "required": False,
                   "description": "Target iframe index (0-based) if element is inside an iframe"},
                  "slow_type": {"type": "boolean", "required": False,
                   "description": "Type character-by-character with delays (for sites that reject instant fill)"}},
                 "judge", _wrap_browser_act),
        ToolSpec("browser_handle_dialog",
                 "Accept or dismiss a browser dialog (alert, confirm, prompt). "
                 "Check browser_snapshot for pending dialog notifications before using.",
                 "browser",
                 {"accept": {"type": "boolean", "required": False,
                  "description": "True to click OK/Accept (default), False to click Cancel/Dismiss"},
                  "prompt_text": {"type": "string", "required": False,
                  "description": "Text to enter for prompt-type dialogs before accepting"}},
                 "judge", _wrap_browser_handle_dialog),
        ToolSpec("browser_get_interactive_elements",
                 "DEPRECATED: prefer browser_snapshot which returns richer Accessibility Tree with Ref IDs. "
                 "Discovers all interactive elements on the page. Returns selectors for browser_type, browser_click.",
                 "browser",
                 {"selector_scope": {"type": "string", "required": False,
                  "description": "Optional CSS selector to scope the search. Defaults to the whole page."}},
                 "safe", _wrap_browser_get_interactive_elements),
        ToolSpec("browser_switch_to_frame",
                 "Get info about a specific iframe by its index",
                 "browser",
                 {"frame_index": {"type": "number", "required": True}},
                 "safe", _wrap_browser_switch_to_frame),

        # ---- Autonomous Browser Agent ----
        ToolSpec("browser_task",
                 "FULLY AUTONOMOUS browsing. Give it a single natural-language command and it navigates, "
                 "snapshots, fills forms, clicks, scrolls, and completes the task on its own. Use this for any multi-step web task: "
                 "'search for flights to NYC next Tuesday', 'find the price of X on Amazon', 'fill out and "
                 "submit the form at <url>', 'log in to <site> and download my report'. "
                 "Uses the built-in browser agent by default, or the external browser-use library when "
                 "browser_automation.provider is 'browseruse'. "
                 "Pass the full command in 'task'; optionally pass 'start_url' to begin on a specific page.",
                 "browser",
                 {"task": {"type": "string", "required": True,
                   "description": "The full natural-language command describing what to accomplish"},
                  "start_url": {"type": "string", "required": False,
                   "description": "Optional URL to start from before working toward the goal"}},
                 "judge", _wrap_browser_task),

        # ---- Browser Use (Agent Provider) ----
        ToolSpec("browser_use_task", "Delegates a complex browsing task to the external browser-use library, forcing that engine regardless of the configured provider. The agent navigates, interacts, and completes the task on its own. Provide a clear, detailed task description. NOTE: requires the 'browser-use' Python package.", "browser",
                 {"task": {"type": "string", "required": True, "description": "The natural-language browsing task to execute"},
                  "start_url": {"type": "string", "required": False, "description": "Optional starting URL for the task"},
                  "model": {"type": "string", "required": False, "description": "Optional model override (e.g. gpt-4o, claude-3-5-sonnet-latest)"}},
                 "judge", _wrap_browser_use_task),

        # ---- Browser Human Takeover (HIL) ----
        ToolSpec("browser_human_takeover", "Pauses autonomous browser execution and requests human takeover/intervention in the browser to solve a CAPTCHA, 2FA prompt, OAuth login, or manual roadblock. Blocks until the user completes the action.", "browser",
                 {"reason": {"type": "string", "required": True, "description": "Explanation of what the human user needs to do in the browser"}},
                 "safe", _wrap_browser_human_takeover),
        ToolSpec("browser_wait_for_human", "Alias for browser_human_takeover. Pauses autonomous browser execution and requests human takeover.", "browser",
                 {"reason": {"type": "string", "required": True, "description": "Explanation of what the human user needs to do in the browser"}},
                 "safe", _wrap_browser_human_takeover),

        # ---- Coordination ----
        ToolSpec("spawn_agent", "Spawn a teammate's ReACT loop with a task", "coordination",
                 {"agent_name": {"type": "string", "required": True},
                  "task": {"type": "string", "required": True}},
                 "safe", _wrap_spawn_agent),
        ToolSpec("create_team_agent", "Create a permanent AI teammate / agent in this team. Use this when the user asks to add, recruit, or hire a permanent team member (e.g. 'add a software engineer to our team', 'create a teammate named Alex'). The agent will remain permanently in the team roster.", "coordination",
                 {"name": {"type": "string", "required": True, "description": "The name of the new teammate (e.g. 'Alex', 'Dev', 'Coder')"},
                  "role": {"type": "string", "required": True, "description": "The role title (e.g. 'Software Engineer', 'QA Specialist', 'Backend Developer')"},
                  "expertise": {"type": "string", "required": False, "description": "Specialization, skills, and background instructions for this agent"},
                  "system_prompt": {"type": "string", "required": False, "description": "Optional custom system prompt"},
                  "model": {"type": "string", "required": False, "description": "Optional model override (e.g. 'openrouter/openai/gpt-4o')"}},
                 "safe", _wrap_create_team_agent),
        ToolSpec("update_team_agent", "Update an existing teammate / agent's profile, role, expertise, model, or personality. Use this when the user asks to modify, update, reassign, or change a team member's configuration (e.g. 'update Alex's role to Principal Engineer', 'change Alex's model to gpt-4o').", "coordination",
                 {"name_or_id": {"type": "string", "required": True, "description": "The name or ID of the teammate to update (e.g. 'Alex' or '@Alex')"},
                  "new_name": {"type": "string", "required": False, "description": "Optional new name for the agent"},
                  "role": {"type": "string", "required": False, "description": "New role title"},
                  "expertise": {"type": "string", "required": False, "description": "Updated specialization or skills"},
                  "model": {"type": "string", "required": False, "description": "New model override"},
                  "personality": {"type": "string", "required": False, "description": "New personality tone"},
                  "custom_instructions": {"type": "string", "required": False, "description": "Custom instructions"}},
                 "safe", _wrap_update_team_agent),
        ToolSpec("delete_team_agent", "Permanently remove a teammate / agent from the team roster. Use this when the user asks to remove, fire, or delete an agent from the team (e.g. 'remove Alex from the team', 'delete agent Dev'). Cannot delete the team Coordinator.", "coordination",
                 {"name_or_id": {"type": "string", "required": True, "description": "The name or ID of the teammate to remove (e.g. 'Alex' or '@Alex')"}},
                 "safe", _wrap_delete_team_agent),
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
        ToolSpec("create_task", "Create a task on the team board with structured specifications. NOTE: This adds the task to the UI board. To execute immediately, follow up with `spawn_agent`.", "task",
                 {"title": {"type": "string", "required": True},
                  "description": {"type": "string", "required": False},
                  "priority": {"type": "string", "required": False},
                  "assignee": {"type": "string", "required": False},
                  "blocked_by_task_id": {"type": "string", "required": False, "description": "ID of a task that must be completed before this task can start"},
                  "depends_on": {"type": "array", "required": False, "description": "List of task IDs or titles that must be completed before this task can start (DAG)"},
                  "target_files": {"type": "array", "required": False, "description": "Optional list of files/directories scoped to this task"},
                  "contract_spec": {"type": "string", "required": False, "description": "Optional shared interface, types, or API models to implement"},
                  "verification_command": {"type": "string", "required": False, "description": "Optional command to verify completion (e.g. pytest tests/test_planner.py)"}},
                 "safe", _wrap_create_task),
        ToolSpec("list_tasks", "List tasks on the team board", "task",
                 {"status": {"type": "string", "required": False}},
                 "safe", _wrap_list_tasks),
        ToolSpec("update_task", "Update a task's status and/or assign it to a teammate by name", "task",
                 {"task_id": {"type": "string", "required": True},
                  "status": {"type": "string", "required": False},
                  "notes": {"type": "string", "required": False},
                  "assignee_name": {"type": "string", "required": False, "description": "Name of the agent to assign the task to"},
                  "blocked_by_task_id": {"type": "string", "required": False, "description": "ID of a task that must be completed before this task can start"},
                  "depends_on": {"type": "array", "required": False, "description": "Updated list of task IDs that must be completed before this task can start"}},
                 "safe", _wrap_update_task),
        ToolSpec("comment_on_task", "Add a comment to a task", "task",
                 {"task_id": {"type": "string", "required": True},
                  "text": {"type": "string", "required": True}},
                 "safe", _wrap_comment_on_task),

        ToolSpec("write_task_plan",
                 "Write an implementation plan for a task in Markdown format. "
                 "This saves the plan to disk and the database, then requests admin approval "
                 "(or auto-approves if auto_approve_plans is enabled for this agent). "
                 "ONLY call this for complex tasks that warrant upfront planning. "
                 "Do NOT begin execution until the plan status is 'approved'.",
                 "task",
                 {"task_id": {"type": "string", "required": True, "description": "Task ID, short prefix, or title"},
                  "plan_markdown": {"type": "string", "required": True, "description": "Full implementation plan in Markdown format"}},
                 "safe", _wrap_write_task_plan),

        ToolSpec("request_plan_approval",
                 "Re-submit a revised implementation plan for admin approval after addressing review comments. "
                 "Use this after updating the plan markdown in response to feedback.",
                 "task",
                 {"task_id": {"type": "string", "required": True}},
                 "safe", _wrap_request_plan_approval),

        ToolSpec("update_task_todos",
                 "Create or update the interactive todo checklist for a task. "
                 "Use 'todos' to set the full list, or 'toggle_id' to flip a single item's done state. "
                 "The checklist appears live on the Kanban card.",
                 "task",
                 {"task_id": {"type": "string", "required": True},
                  "todos": {"type": "array", "required": False,
                            "description": "List of {id, text, done} objects. Replaces existing list."},
                  "toggle_id": {"type": "string", "required": False,
                                "description": "ID of a single todo item to toggle done/undone."}},
                 "safe", _wrap_update_task_todos),

        # ---- Scheduled Tasks (Cron) ----
        ToolSpec("create_scheduled_task",
                 "Create a recurring scheduled task that will automatically trigger an agent with a prompt on a cron schedule. "
                 "Use standard 5-field cron syntax: '*/2 * * * *' = every 2 mins, '0 9 * * 1-5' = 9am weekdays, '0 * * * *' = hourly. "
                 "The task will be stored in the database and picked up by the background cron worker automatically.",
                 "scheduler",
                 {"name": {"type": "string", "required": True, "description": "Human-readable name for this scheduled task, e.g. 'Check Tech News'"},
                  "cron_expression": {"type": "string", "required": True, "description": "5-field cron expression, e.g. '*/2 * * * *' for every 2 minutes"},
                  "prompt": {"type": "string", "required": True, "description": "The exact prompt text the agent will receive when this task triggers. Be specific and self-contained."}},
                 "safe", _wrap_create_scheduled_task),
        ToolSpec("list_scheduled_tasks",
                 "List all scheduled tasks for the current team, including their status (active/paused), cron expression, and last run time.",
                 "scheduler", {},
                 "safe", _wrap_list_scheduled_tasks),
        ToolSpec("update_scheduled_task",
                 "Update a scheduled task: pause/resume it, change its cron schedule, or change the prompt it sends. Provide only the fields you want to change.",
                 "scheduler",
                 {"task_id": {"type": "string", "required": True, "description": "The UUID of the scheduled task to update"},
                  "is_active": {"type": "boolean", "required": False, "description": "true to resume, false to pause"},
                  "cron_expression": {"type": "string", "required": False, "description": "New cron schedule"},
                  "prompt": {"type": "string", "required": False, "description": "New prompt content"},
                  "name": {"type": "string", "required": False, "description": "New display name"}},
                 "safe", _wrap_update_scheduled_task),
        ToolSpec("delete_scheduled_task",
                 "Permanently delete a scheduled task so it will never run again.",
                 "scheduler",
                 {"task_id": {"type": "string", "required": True, "description": "The UUID of the scheduled task to delete"}},
                 "judge", _wrap_delete_scheduled_task),

        # ---- Interaction ----
        ToolSpec("ask_user",
                 "Ask the human clarifying question(s) and wait for their response. "
                 "Supports either a single 'question' with optional 'options', OR a 'questions' array "
                 "to ask multiple questions at once with options (single or multi-select) plus custom text. "
                 "Always batch related questions together in 'questions' to save tokens and roundtrips.",
                 "interaction",
                 {"question": {"type": "string", "required": False, "description": "Single question text"},
                  "options": {"type": "array", "required": False, "description": "Optional list of choice strings for single question"},
                  "questions": {"type": "array", "required": False,
                                "description": "List of question objects: [{'id': 'q1', 'question': '...', 'options': ['opt1', 'opt2'], 'is_multi_select': False}]"}},
                 "safe", _wrap_ask_user),
        ToolSpec("fetch_tool_schemas",
                 "On-demand tool discovery. Request and activate full tool schemas for a specific tool family "
                 "(e.g. 'git', 'browser', 'meetings', 'shell', 'database') or specific tool names. "
                 "Use this when you need specialized tools outside your initial role toolset.",
                 "coordination",
                 {"family": {"type": "string", "required": False, "description": "Tool family name (e.g. 'git', 'browser', 'meetings', 'shell')"},
                  "tool_names": {"type": "array", "required": False, "description": "Specific tool names to activate"}},
                 "safe", _wrap_fetch_tool_schemas),
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
        ToolSpec("add_memory",
                 "Save an important fact or lesson directly to long-term archival memory. "
                 "Use this proactively during tasks to preserve critical information that "
                 "might otherwise be lost to context compaction.",
                 "memory",
                 {"topic": {"type": "string", "required": True,
                            "description": "Short title / context for the memory (e.g. 'User database setup')"},
                  "content": {"type": "string", "required": True,
                              "description": "The actual lesson, fact, or information to remember"}},
                 "safe", _wrap_add_memory),
        ToolSpec("search_memory",
                 "Search long-term archival memory for relevant past learnings. "
                 "Use this when you need to recall context that has been compacted out of the conversation.",
                 "memory",
                 {"query": {"type": "string", "required": True,
                            "description": "Natural language description of what to search for"},
                  "limit": {"type": "integer", "required": False,
                            "description": "Max number of results to return (default 5)"}},
                 "safe", _wrap_search_memory),
        ToolSpec("add_fact",
                 "Save a named fact (key=value) to the entity memory store. "
                 "Facts are always injected into the system prompt, so they are never compacted away. "
                 "Use for critical persistent information like user preferences, project settings, etc.",
                 "memory",
                 {"key": {"type": "string", "required": True,
                          "description": "Short snake_case name for the fact (e.g. 'user_preferred_language')"},
                  "value": {"type": "string", "required": True,
                            "description": "The value to store (e.g. 'TypeScript')"}},
                 "safe", _wrap_add_fact),
        ToolSpec("edit_fact",
                 "Update the value of an existing named fact in entity memory.",
                 "memory",
                 {"key": {"type": "string", "required": True},
                  "new_value": {"type": "string", "required": True}},
                 "safe", _wrap_edit_fact),
        ToolSpec("delete_fact",
                 "Remove a named fact from the entity memory store.",
                 "memory",
                 {"key": {"type": "string", "required": True}},
                 "safe", _wrap_delete_fact),
                 
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

    ToolRegistry.register_batch(builtins, force=True)
    _builtins_registered = True
    logger.info("🔧 [ToolRegistry] Registered %d built-in tools.", len(builtins))


# ============================================================
# Access Control Infrastructure
# ============================================================

# Map UI permission levels → internal gate levels
_PERM_ALIAS: Dict[str, str] = {
    "allow":            "safe",
    "judge":            "judge",
    "always_ask":       "human",
    "require_approval": "judge",
    "block":            "block",
    # legacy aliases
    "safe":             "safe",
    "human":            "human",
}

# Map tool names → high-level action category
_TOOL_CATEGORY: Dict[str, str] = {
    # view / read
    "read_file": "view", "list_directory": "view", "grep_search": "view",
    "glob_search": "view", "diff_files": "view", "find_function": "view",
    "find_todos": "view", "count_lines": "view", "analyze_imports": "view",
    "check_syntax": "view", "analyze_impact": "view", "workspace_tree": "view",
    "find_symbol_definition": "view", "get_file_outline": "view",
    "get_symbol_callers": "view", "get_symbol_callees": "view",
    "read_scratchpad": "view",
    # edit
    "edit_file": "edit", "append_file": "edit",
    # create / write
    "write_file": "create", "create_directory": "create",
    "copy_file": "create", "move_file": "create",
    # delete
    "delete_file": "delete",
    # execute / shell / raw http
    "execute_command": "execute", "http_request": "execute",
    # git
    "git_status": "git", "git_diff": "git", "git_log": "git",
    "git_add": "git", "git_commit": "git", "git_push": "git",
    "git_pull": "git", "git_branch": "git", "git_checkout": "git",
    "git_stash": "git", "git_clone": "git",
    # web
    "web_search": "web", "web_fetch": "web", "web_extract_links": "web",
    # browser
    "browser_navigate": "browser", "browser_click": "browser",
    "browser_click_text": "browser", "browser_type": "browser",
    "browser_press_key": "browser", "browser_select_option": "browser",
    "browser_checkbox": "browser", "browser_screenshot": "browser",
    "browser_screenshot_element": "browser", "browser_get_text": "browser",
    "browser_get_html": "browser", "browser_eval_js": "browser",
    "browser_wait": "browser", "browser_scroll": "browser",
    "browser_hover": "browser", "browser_clear_cookies": "browser",
    "join_meeting": "browser", "join_google_meet": "browser",
    "send_google_meet_chat": "browser",
    "browser_snapshot": "browser", "browser_act": "browser",
    "browser_handle_dialog": "browser", "browser_task": "browser",
    "browser_use_task": "browser", "browser_human_takeover": "browser",
    "browser_wait_for_human": "browser", "browser_extract_text": "browser",
    "browser_extract_html": "browser", "browser_switch_to_frame": "browser",
    # scratchpad / state
    "write_scratchpad": "edit", "update_scratchpad": "edit", "clear_scratchpad": "delete",
    # memory
    "add_memory": "create", "update_memory": "edit", "forget_memory": "delete", "search_memory": "view",
    "add_fact": "create", "edit_fact": "edit", "delete_fact": "delete",
    # subagents
    "spawn_agent": "subagents", "hire_subagent": "subagents",
    "create_team_agent": "subagents",
    "update_team_agent": "subagents",
    "delete_team_agent": "subagents",
    "send_message": "subagents", "team_broadcast": "subagents",
    "delegate_subtask": "subagents",
    # scheduler
    "create_scheduled_task": "scheduler", "list_scheduled_tasks": "scheduler",
    "update_scheduled_task": "scheduler", "delete_scheduled_task": "scheduler",
}

# Default gate level per category when no override exists
_CATEGORY_DEFAULTS: Dict[str, str] = {
    "view":      "safe",
    "edit":      "judge",
    "create":    "judge",
    "delete":    "human",
    "execute":   "judge",
    "git":       "safe",
    "web":       "safe",
    "browser":   "safe",
    "subagents": "safe",
    "scheduler": "judge",
}


def _get_effective_permissions(permissions: Any) -> Dict[str, Any]:
    """
    Combines agent-level permissions with global system defaults from ~/.carole/config.json.
    """
    from core.llm.config_manager import load_config
    global_cfg = load_config().get("access_control", {})
    if not isinstance(permissions, dict):
        permissions = {}

    # If it's a flat dict like {"read_file": "safe", "subagents": "block"}, separate categories from tool overrides
    if "categories" not in permissions and any(isinstance(v, str) for v in permissions.values() if not str(v).startswith("__")):
        known_categories = set(_CATEGORY_DEFAULTS.keys()) | set(_TOOL_CATEGORY.values())
        flat_categories = {}
        flat_overrides = {}
        for k, v in permissions.items():
            if isinstance(v, str) and not k.startswith("__"):
                if k in known_categories:
                    flat_categories[k] = v
                else:
                    flat_overrides[k] = v

        return {
            "enable_judge": global_cfg.get("enable_judge", True),
            "judge_fallback": global_cfg.get("judge_fallback", "always_ask"),
            "categories": {**_CATEGORY_DEFAULTS, **global_cfg.get("categories", {}), **flat_categories},
            "overrides": {**global_cfg.get("overrides", {}), **flat_overrides},
            "custom_skip_judge": global_cfg.get("custom_skip_judge", {"file_patterns": [], "command_prefixes": []}),
        }

    # Structured config: merge agent with global defaults
    merged_categories = {**_CATEGORY_DEFAULTS, **global_cfg.get("categories", {}), **permissions.get("categories", {})}
    merged_overrides = {**global_cfg.get("overrides", {}), **permissions.get("overrides", {})}
    
    global_skip = global_cfg.get("custom_skip_judge", {})
    agent_skip = permissions.get("custom_skip_judge", {})
    merged_file_patterns = list(dict.fromkeys(
        (global_skip.get("file_patterns") or []) + (agent_skip.get("file_patterns") or [])
    ))
    merged_cmd_prefixes = list(dict.fromkeys(
        (global_skip.get("command_prefixes") or []) + (agent_skip.get("command_prefixes") or [])
    ))

    return {
        "enable_judge": permissions.get("enable_judge", global_cfg.get("enable_judge", True)),
        "judge_fallback": permissions.get("judge_fallback", global_cfg.get("judge_fallback", "always_ask")),
        "categories": merged_categories,
        "overrides": merged_overrides,
        "custom_skip_judge": {
            "file_patterns": merged_file_patterns,
            "command_prefixes": merged_cmd_prefixes,
        },
    }


_GATE_RANK = {
    "safe": 0,
    "judge": 1,
    "human": 2,
    "block": 3,
}


def _normalize_gate(value: Any) -> str:
    if not isinstance(value, str):
        return "block"
    normalized = _PERM_ALIAS.get(value, value)
    return normalized if normalized in _GATE_RANK else "block"


def _resolve_gate_level(
    tool_name: str,
    permissions: Dict[str, Any],
) -> str:
    spec = ToolRegistry.get(tool_name)
    if spec is None:
        return "block"

    baseline = _normalize_gate(spec.permission_default)
    category = _TOOL_CATEGORY.get(tool_name, spec.category)

    categories = permissions.get("categories", {})
    overrides = permissions.get("overrides", {})

    if not isinstance(categories, dict) or not isinstance(overrides, dict):
        return "block"

    category_gate = _normalize_gate(
        categories.get(category, baseline)
    )
    override_gate = _normalize_gate(
        overrides.get(tool_name, baseline)
    )

    return max(
        (baseline, category_gate, override_gate),
        key=_GATE_RANK.__getitem__,
    )


def _matches_skip_judge(tool_name: str, arguments: Dict[str, Any], permissions: Dict[str, Any]) -> bool:
    """
    Returns True if the tool call matches a user-configured skip-judge
    whitelist entry, allowing it to bypass Judge evaluation and execute
    instantly (same as 'safe').
    """
    skip = permissions.get("custom_skip_judge", {})
    if not skip:
        return False

    import fnmatch

    # File-pattern whitelist — applies to file tools
    file_patterns = skip.get("file_patterns", [])
    if file_patterns and tool_name in {"write_file", "edit_file", "append_file", "read_file", "copy_file", "move_file", "delete_file"}:
        path = (arguments.get("relative_path") or arguments.get("path") or
                arguments.get("source") or arguments.get("destination") or
                arguments.get("value") or "")
        if path:
            norm_path = path.replace("\\", "/")
            for pat in file_patterns:
                norm_pat = pat.replace("\\", "/")
                if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(norm_path, norm_pat):
                    return True

    # Command-prefix whitelist — applies to execute_command
    cmd_prefixes = skip.get("command_prefixes", [])
    if cmd_prefixes and tool_name == "execute_command":
        cmd = arguments.get("command") or arguments.get("value") or ""
        if cmd:
            cmd_stripped = cmd.strip()
            for prefix in cmd_prefixes:
                if cmd_stripped.startswith(prefix.strip()):
                    return True

    return False


def _apply_judge_disabled_fallback(permissions: Dict[str, Any]) -> str:
    """
    When the Judge LLM is disabled (enable_judge=False), return the
    configured fallback gate level for actions nominally set to 'judge'.

      judge_fallback='allow'      → 'safe'   (Autonomy mode)
      judge_fallback='always_ask' → 'human'  (Strict mode, default)
    """
    fallback = permissions.get("judge_fallback", "always_ask")
    if fallback == "allow":
        return "safe"
    return "human"


async def _wrap_browser_task(args: Dict[str, Any], team_id: str) -> str:
    task = args.get("task") or args.get("command") or args.get("value", "")
    if not task:
        return "Error: 'task' is required."
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    start_url = args.get("start_url")

    # Prefer the agent's own model so reasoning quality matches its config.
    import core.config
    model = getattr(core.config, "DEFAULT_SMART_MODEL", "openrouter/free")
    try:
        from core.memory.database import async_session
        from core.memory.models import Agent as DbAgent
        from sqlalchemy import select
        async with async_session() as db:
            record = (await db.execute(select(DbAgent).where(DbAgent.id == agent_id))).scalar_one_or_none()
            if record and record.model:
                model = record.model
    except Exception:
        pass

    # Honor the configured provider. Selecting "Browser Use (Agent)" in Settings
    # routes the autonomous task through the external browser-use library; every
    # other provider uses the built-in BrowserAgent, which inherits the shared
    # Playwright pool and its Browserbase / proxy / stealth settings.
    from core.llm.config_manager import load_config
    provider = load_config().get("browser_automation", {}).get("provider", "local")
    if provider == "browseruse":
        return await _wrap_browser_use_task({"task": task, "_agent_id": agent_id, "start_url": start_url}, team_id)

    from core.tools.browser_agent import BrowserAgent
    agent = BrowserAgent(model=model)
    return await agent.run(task, agent_id, agent_name, team_id, start_url=start_url)


async def _wrap_browser_use_task(args: Dict[str, Any], team_id: str) -> str:
    try:
        from browser_use import Agent as BrowserUseAgent
    except ImportError:
        return ("Error: the 'browser-use' package is not installed. "
                "Run `pip install browser-use` (listed in requirements.txt).")
    from core.memory.database import async_session
    from core.memory.models import Agent as DbAgent
    from sqlalchemy import select
    import asyncio
    import os

    task = args.get("task") or args.get("prompt") or args.get("command") or args.get("instruction") or ""
    if not task or not str(task).strip():
        return "Error: task is required."

    start_url = args.get("start_url") or args.get("url")
    if start_url and str(start_url) not in str(task):
        task = f"Navigate to {start_url} and then: {task}"

    agent_id = args.get("_agent_id")
    import core.config

    # 1. Model priority: explicit argument -> database agent -> configured default
    model_name = args.get("model")
    if not model_name and agent_id:
        try:
            import uuid
            agent_uuid = uuid.UUID(str(agent_id))
            async with async_session() as db:
                agent_record = (await db.execute(select(DbAgent).where(DbAgent.id == agent_uuid))).scalar_one_or_none()
                if agent_record and agent_record.model:
                    model_name = agent_record.model
        except Exception:
            pass

    try:
        from core.llm.config_manager import load_config, get_key, get_browser_key
        cfg = load_config() or {}

        ba_cfg = cfg.get("browser_automation", {})
        provider = ba_cfg.get("provider", "local")

        # Consolidate API keys strictly using config isolation (no host env leak if cfg has keys)
        keys = {
            "openai": get_key(cfg, "openai", "OPENAI_API_KEY"),
            "anthropic": get_key(cfg, "anthropic", "ANTHROPIC_API_KEY"),
            "google": get_key(cfg, "google", "GOOGLE_API_KEY") or get_key(cfg, "google", "GEMINI_API_KEY"),
            "openrouter": get_key(cfg, "openrouter", "OPENROUTER_API_KEY"),
            "browserbase": get_browser_key(cfg, "browserbase", "BROWSERBASE_API_KEY"),
        }

        if not model_name:
            if keys.get("openai"):
                model_name = "gpt-4o"
            elif keys.get("anthropic"):
                model_name = "claude-3-5-sonnet-latest"
            elif keys.get("google"):
                model_name = "gemini-2.0-flash"
            elif keys.get("openrouter"):
                model_name = "openrouter/auto"
            else:
                model_name = getattr(core.config, "DEFAULT_SMART_MODEL", "gpt-4o")

        try:
            from browser_use import Browser, BrowserProfile
            from urllib.parse import urlencode
            bb_key = keys.get("browserbase")
            project_id = ba_cfg.get("project_id") or cfg.get("project_id")
            if (provider == "browserbase" or ba_cfg.get("infrastructure") == "browserbase") and bb_key:
                params = {"apiKey": bb_key}
                if project_id and str(project_id).strip():
                    params["projectId"] = str(project_id).strip()
                browser_instance = Browser(cdp_url="wss://connect.browserbase.com?" + urlencode(params))
            else:
                headless = ba_cfg.get("display_mode") != "windowed" and ba_cfg.get("headless") is not False
                try:
                    browser_instance = Browser(browser_profile=BrowserProfile(headless=headless))
                except Exception:
                    browser_instance = Browser()
        except Exception:
            browser_instance = None

        llm = None
        model_lower = str(model_name).lower()

        # Adaptive provider resolution: if requested provider lacks an API key, switch to an available one
        if "gemini" in model_lower and not (keys.get("google") or keys.get("browseruse")):
            if keys.get("openai"):
                model_name, model_lower = "gpt-4o", "gpt-4o"
            elif keys.get("openrouter"):
                model_name, model_lower = "openrouter/auto", "openrouter/auto"
            elif keys.get("anthropic"):
                model_name, model_lower = "claude-3-5-sonnet-latest", "claude-3-5-sonnet-latest"
        elif "claude" in model_lower and not (keys.get("anthropic") or keys.get("browseruse")):
            if keys.get("openai"):
                model_name, model_lower = "gpt-4o", "gpt-4o"
            elif keys.get("google"):
                model_name, model_lower = "gemini-2.0-flash", "gemini-2.0-flash"
        elif "openrouter" in model_lower and not (keys.get("openrouter") or keys.get("browseruse")):
            if keys.get("openai"):
                model_name, model_lower = "gpt-4o", "gpt-4o"

        if "openrouter" in model_lower:
            from langchain_openai import ChatOpenAI
            api_key = keys.get("openrouter") or keys.get("browseruse")
            if not api_key: return "Error: OpenRouter API key is missing. Required for this agent."
            actual_model = model_name[11:] if model_lower.startswith("openrouter/") else model_name
            llm = ChatOpenAI(
                model=actual_model,
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1"
            )
        elif "claude" in model_lower:
            from langchain_anthropic import ChatAnthropic
            api_key = keys.get("anthropic") or keys.get("browseruse")
            if not api_key: return "Error: Anthropic API key is missing. Required for this agent."
            llm = ChatAnthropic(model=model_name, api_key=api_key)
        elif "gemini" in model_lower:
            from langchain_google_genai import ChatGoogleGenerativeAI
            api_key = keys.get("google") or keys.get("browseruse")
            if not api_key: return "Error: Google API key is missing. Required for this agent."
            llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key)
        else:
            from langchain_openai import ChatOpenAI
            api_key = keys.get("openai") or keys.get("browseruse")
            if not api_key: return "Error: OpenAI API key is missing. Required for browser-use."

            if "/" in model_name: 
                model_name = model_name.split("/")[-1]

            llm = ChatOpenAI(model=model_name, api_key=api_key)

        agent = BrowserUseAgent(task=task, llm=llm, browser=browser_instance)
        try:
            result = await agent.run()
            return f"Browser Use Agent finished. Result:\n{result}"
        finally:
            if browser_instance is not None:
                try:
                    await browser_instance.close()
                except Exception:
                    pass
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Browser Use task failed: {e}")
        return f"Error running browser use task: {e}"


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

        # ── Scope enforcement (Recommendation 7.A) ──
        if spec.team_id is not None and str(spec.team_id) != str(team_id):
            return "Execution Denied: Tool is not available to this team."
        if spec.agent_id is not None and str(spec.agent_id) != str(agent_id):
            return "Execution Denied: Tool is not available to this agent."

        # ── Orchestrator Role Guard ──
        # Orchestrators/Coordinators are hard-blocked from modifying project source code files directly,
        # but ARE permitted to author planning/documentation Markdown files (*.md, *.markdown).
        if context and getattr(context, "agent_role", None) in ("Orchestrator", "Coordinator"):
            if tool_name in ("write_file", "edit_file", "append_file"):
                rel = str(arguments.get("relative_path") or arguments.get("path") or arguments.get("filename") or "").strip()
                is_md = rel.lower().endswith((".md", ".markdown"))
                if not is_md:
                    return (
                        "Execution Denied: As an Orchestrator, you must NOT write or modify project files directly. "
                        "Break the task down, create a task and assign it to the respective member of your team roster "
                        "(e.g. create_task with assignee_name), or delegate using spawn_agent."
                    )
            elif tool_name in ("create_directory", "delete_file"):
                return (
                    "Execution Denied: As an Orchestrator, you must NOT write or modify project files directly. "
                    "Break the task down, create a task and assign it to the respective member of your team roster "
                    "(e.g. create_task with assignee_name), or delegate using spawn_agent."
                )

        # ── Pre-validation & Sanitization of arguments ──
        # Strip reserved internal arguments to prevent authorization forgery (Recommendation 7.D)
        RESERVED_ARGS = {
            "_human_confirmed", "_server_approved", "_context",
            "_agent_id", "_agent_name", "_team_id", "_active_message_id",
            "confirm_destructive",
        }
        arguments = {k: v for k, v in arguments.items() if k not in RESERVED_ARGS}

        # Check for placeholder Ellipsis or empty/placeholder values
        if arguments:
            has_ellipsis = False
            if "_positional_args" in arguments:
                pos = arguments["_positional_args"]
                if any(x is Ellipsis or x == "Ellipsis" or str(x) == "Ellipsis" or x == "..." for x in pos):
                    has_ellipsis = True
            for k, v in arguments.items():
                if v is Ellipsis or v == "Ellipsis" or str(v) == "Ellipsis" or v == "...":
                    has_ellipsis = True
            if has_ellipsis:
                return (f"Error: Tool '{tool_name}' arguments contains placeholder 'Ellipsis' (...). "
                        "Do not use placeholders. Provide actual parameter values.")

        # Check required parameters
        if spec.parameters:
            for param_name, param_info in spec.parameters.items():
                if param_info.get("required", False):
                    if param_name not in arguments or arguments[param_name] is None or str(arguments[param_name]).strip() == "":
                        usage_parts = [f'{k}="..."' if v.get("required", False) else f'[{k}="..."]' for k, v in spec.parameters.items()]
                        usage_str = f"{tool_name}({', '.join(usage_parts)})"
                        return f"Error: Missing required parameter '{param_name}'. Usage: {usage_str}"

        # ── Granular runtime context (always_deny / always_allow) takes top priority ──
        if permission_context:
            if tool_name in permission_context.always_deny:
                logger.info("🛑 [Executor] Tool '%s' denied by always_deny rule.", tool_name)
                return f"✗ Execution Cancelled: '{tool_name}' is explicitly denied by permission context."
            if tool_name in permission_context.always_allow:
                logger.info("✓ [Executor] Tool '%s' allowed by always_allow rule.", tool_name)
                return await self._run_tool(spec, arguments, agent_id, agent_name, team_id, active_message_id, context)

        # ── Permission resolution ─────────────────────────────────────────────
        effective_permissions = _get_effective_permissions(permissions)
        gate_level = _resolve_gate_level(tool_name, effective_permissions)

        # 1. Block — hard deny, no override, no evaluation
        if gate_level == "block":
            # Allow Orchestrator/Coordinator to write .md documentation even if the role default had write_file blocked
            if context and getattr(context, "agent_role", None) in ("Orchestrator", "Coordinator") and _is_doc_write(tool_name, arguments):
                pass
            else:
                logger.info("🛑 [Executor] Tool '%s' blocked by access control policy.", tool_name)
                return (f"✗ Execution Blocked: '{tool_name}' is disabled by your Access Control policy. "
                        "Update permissions in Agent Settings → Access Control.")

        # 2. Skip-judge whitelist fast-path
        if gate_level == "judge" and _matches_skip_judge(tool_name, arguments, effective_permissions):
            logger.info("⚡ [Executor] Skip-judge whitelist match for '%s'.", tool_name)
            gate_level = "safe"

        # 3. Judge disabled → apply fallback
        if gate_level == "judge" and not effective_permissions.get("enable_judge", True):
            gate_level = _apply_judge_disabled_fallback(effective_permissions)
            logger.info("⚡ [Executor] Judge disabled — fallback gate='%s' for '%s'.", gate_level, tool_name)

        # Phase 5: Destructive Command Guardrail — Escalate directly to Human-in-the-Loop modal
        if tool_name == "execute_command":
            import re
            cmd = arguments.get("command") or arguments.get("value") or ""
            destructive_patterns = [
                r"\brm\s+-(?:[a-zA-Z]*[rf][a-zA-Z]*)\b",
                r"\bdrop\s+(?:table|database|schema)\b",
                r"\bgit\s+reset\s+--hard\b",
                r"\bgit\s+clean\s+-(?:[a-zA-Z]*f[a-zA-Z]*)\b",
                r"\btruncate\s+table\b",
            ]
            if any(re.search(pat, cmd, re.IGNORECASE) for pat in destructive_patterns):
                logger.warning("🛑 High-risk destructive command: '%s'. Escalating gate to 'human'.", cmd)
                gate_level = "human"

        # ── Documentation fast-path (frictionless .md/.txt writes) ───────────
        if _is_doc_write(tool_name, arguments):
            logger.info("📝 [Executor] Frictionless doc write for '%s' (tool=%s).", agent_name, tool_name)
            return await self._run_tool(spec, arguments, agent_id, agent_name, team_id, active_message_id, context)

        # ── Implementation Plan Approval Guard ────────────────────────────────
        # If the agent has a task currently awaiting human plan approval, block
        # mutating file actions and shell execution until approved.
        if tool_name in ("write_file", "edit_file", "append_file", "delete_file", "execute_command"):
            try:
                from core.memory.database import async_session
                from core.memory.models import Task
                from sqlalchemy import select
                agent_uuid = uuid.UUID(agent_id) if isinstance(agent_id, str) else agent_id
                async with async_session() as db:
                    stmt_plan = select(Task).where(
                        Task.assigned_agent_id == agent_uuid,
                        Task.plan_status == "awaiting_approval"
                    ).limit(1)
                    pending_plan_task = (await db.execute(stmt_plan)).scalar_one_or_none()
                    if pending_plan_task:
                        logger.warning(
                            "🛑 [Executor] Action '%s' paused for agent '%s': task '%s' plan is awaiting human approval.",
                            tool_name, agent_name, pending_plan_task.title
                        )
                        return (
                            f"🛑 Action Paused: The implementation plan for task '{pending_plan_task.title}' is currently "
                            f"AWAITING HUMAN APPROVAL. You cannot modify code files or execute shell commands until "
                            f"an administrator reviews and approves your plan via the UI."
                        )
            except Exception as e:
                logger.debug("[Executor] Plan approval guard notice: %s", e)

        # ── Gate dispatch ─────────────────────────────────────────────────────
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
            pending_approval_details[tx_id] = {
                "tx_id": tx_id,
                "team_id": str(team_id),
                "agent_id": agent_id,
                "agent_name": agent_name,
                "tool_name": tool_name,
                "arguments": arguments,
                "gate_level": "judge",
                "created_at": time.time(),
            }
            resolved_status = "denied"
            judge_task = None
            human_task = None
            start_monotonic = time.monotonic()
            deadline = start_monotonic + APPROVAL_TIMEOUT_SECS

            try:
                # 1. Publish approval request to UI instantly
                await _publish_approval(topic, {
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

                # 3. Wait for the FIRST one to finish within monotonic deadline
                remaining = max(0.1, deadline - time.monotonic())
                done, pending = await asyncio.wait(
                    [judge_task, human_task],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=remaining,
                )

                if not done:
                    # Both timed out
                    logger.warning("[Executor] Approval for tx_id=%s timed out after %ds.", tx_id, APPROVAL_TIMEOUT_SECS)
                    resolved_status = "denied"
                    await _publish_approval(topic, {
                        "type": "approval_resolved",
                        "tx_id": tx_id,
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "tool_name": tool_name,
                        "status": "denied",
                        "reason": "Timed out waiting for approval"
                    })
                    return f"✗ Approval timed out after {APPROVAL_TIMEOUT_SECS}s: '{tool_name}' was not approved."

                if human_task in done:
                    # Human answered first
                    override_approved = approval_results.get(tx_id, False)

                    if override_approved:
                        logger.info("✓ [Executor] tx_id=%s HUMAN APPROVED (preempted judge).", tx_id)
                        resolved_status = "approved"
                        await _publish_approval(topic, {
                            "type": "approval_resolved",
                            "tx_id": tx_id,
                            "agent_id": agent_id,
                            "agent_name": agent_name,
                            "tool_name": tool_name,
                            "status": "approved",
                            "reason": "Human override approved"
                        })
                        arguments["_server_approved"] = True
                        arguments["_human_confirmed"] = True
                        return await self._run_tool(spec, arguments, agent_id, agent_name, team_id, active_message_id, context)
                    else:
                        logger.info("✗ [Executor] tx_id=%s HUMAN DENIED (preempted judge).", tx_id)
                        resolved_status = "denied"
                        await _publish_approval(topic, {
                            "type": "approval_resolved",
                            "tx_id": tx_id,
                            "agent_id": agent_id,
                            "agent_name": agent_name,
                            "tool_name": tool_name,
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
                        logger.info("✓ [Executor] tx_id=%s JUDGE APPROVED.", tx_id)
                        resolved_status = "approved"

                        # Notify UI that approval is resolved so card can disappear
                        await _publish_approval(topic, {
                            "type": "approval_resolved",
                            "tx_id": tx_id,
                            "agent_id": agent_id,
                            "agent_name": agent_name,
                            "tool_name": tool_name,
                            "status": "approved",
                            "reason": reason
                        })
                        arguments["_server_approved"] = True
                        return await self._run_tool(spec, arguments, agent_id, agent_name, team_id, active_message_id, context)
                    else:
                        # Judge denied. We DO NOT cancel human task. We wait for human override!
                        logger.info("🛑 [Executor] tx_id=%s JUDGE DENIED. Awaiting human override...", tx_id)

                        # Update UI to show denial reason
                        await _publish_approval(topic, {
                            "type": "approval_update",
                            "tx_id": tx_id,
                            "agent_id": agent_id,
                            "agent_name": agent_name,
                            "tool_name": tool_name,
                            "text": f"🛑 Judge DENIED execution: {reason}\nRequire human override to proceed."
                        })

                        # Wait for human task (remaining monotonic deadline)
                        remaining = max(0.1, deadline - time.monotonic())
                        try:
                            await asyncio.wait_for(human_task, timeout=remaining)
                        except asyncio.TimeoutError:
                            logger.warning("[Executor] Override for tx_id=%s timed out.", tx_id)
                            resolved_status = "denied"
                            await _publish_approval(topic, {
                                "type": "approval_resolved",
                                "tx_id": tx_id,
                                "agent_id": agent_id,
                                "agent_name": agent_name,
                                "tool_name": tool_name,
                                "status": "denied",
                                "reason": "Timed out waiting for human override"
                            })
                            return f"✗ Approval timed out after {APPROVAL_TIMEOUT_SECS}s: '{tool_name}' was not approved."

                        override_approved = approval_results.get(tx_id, False)

                        if override_approved:
                            logger.info("✓ [Executor] tx_id=%s OVERRIDE APPROVED. Resuming...", tx_id)
                            resolved_status = "approved"
                            await _publish_approval(topic, {
                                "type": "approval_resolved",
                                "tx_id": tx_id,
                                "agent_id": agent_id,
                                "agent_name": agent_name,
                                "tool_name": tool_name,
                                "status": "approved",
                                "reason": "Human override approved"
                            })
                            arguments["_server_approved"] = True
                            arguments["_human_confirmed"] = True
                            return await self._run_tool(spec, arguments, agent_id, agent_name, team_id, active_message_id, context)
                        else:
                            logger.info("✗ [Executor] tx_id=%s OVERRIDE DENIED.", tx_id)
                            resolved_status = "denied"
                            await _publish_approval(topic, {
                                "type": "approval_resolved",
                                "tx_id": tx_id,
                                "agent_id": agent_id,
                                "agent_name": agent_name,
                                "tool_name": tool_name,
                                "status": "denied",
                                "reason": "Human override denied"
                            })
                            return f"✗ Execution Cancelled: Human operator denied approval to run '{tool_name}' after Judge rejection."
            finally:
                tasks = [
                    task
                    for task in (judge_task, human_task)
                    if task is not None
                ]
                for task in tasks:
                    if not task.done():
                        task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

                pending_approvals.pop(tx_id, None)
                approval_results.pop(tx_id, None)
                pending_approval_details.pop(tx_id, None)
                resolved_approvals[tx_id] = {
                    "tx_id": tx_id,
                    "team_id": str(team_id),
                    "status": resolved_status,
                    "action": "APPROVED" if resolved_status == "approved" else "DENIED",
                    "resolved_at": time.time()
                }
                if len(resolved_approvals) > 500:
                    try:
                        oldest = next(iter(resolved_approvals))
                        resolved_approvals.pop(oldest, None)
                    except Exception:
                        pass

        # 3. Human — block until user approves via POST /api/tools/approve/{tx_id}
        elif gate_level == "human":
            tx_id = str(uuid.uuid4())
            topic = f"team:{team_id}"

            event = asyncio.Event()
            pending_approvals[tx_id] = event
            pending_approval_details[tx_id] = {
                "tx_id": tx_id,
                "team_id": str(team_id),
                "agent_id": agent_id,
                "agent_name": agent_name,
                "tool_name": tool_name,
                "arguments": arguments,
                "gate_level": "human",
                "created_at": time.time(),
            }
            resolved_status = "denied"

            try:
                await _publish_approval(topic, {
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
                    resolved_status = "denied"
                    await _publish_approval(topic, {
                        "type": "approval_resolved",
                        "tx_id": tx_id,
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "tool_name": tool_name,
                        "status": "denied",
                        "reason": "Timed out waiting for approval"
                    })
                    return f"✗ Approval timed out after {APPROVAL_TIMEOUT_SECS}s: '{tool_name}' was not approved."

                approved = approval_results.get(tx_id, False)

                if approved:
                    logger.info("✓ [Executor] tx_id=%s APPROVED. Resuming execution...", tx_id)
                    resolved_status = "approved"
                    await _publish_approval(topic, {
                        "type": "approval_resolved",
                        "tx_id": tx_id,
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "tool_name": tool_name,
                        "status": "approved",
                        "reason": "Human approval granted"
                    })
                    arguments["_server_approved"] = True
                    arguments["_human_confirmed"] = True
                    return await self._run_tool(spec, arguments, agent_id, agent_name, team_id, active_message_id, context)
                else:
                    logger.info("✗ [Executor] tx_id=%s DENIED. Cancelling execution...", tx_id)
                    resolved_status = "denied"
                    await _publish_approval(topic, {
                        "type": "approval_resolved",
                        "tx_id": tx_id,
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "tool_name": tool_name,
                        "status": "denied",
                        "reason": "Human denied"
                    })
                    return f"✗ Execution Cancelled: Human operator denied approval to run '{tool_name}'."
            finally:
                pending_approvals.pop(tx_id, None)
                approval_results.pop(tx_id, None)
                pending_approval_details.pop(tx_id, None)
                resolved_approvals[tx_id] = {
                    "tx_id": tx_id,
                    "team_id": str(team_id),
                    "status": resolved_status,
                    "action": "APPROVED" if resolved_status == "approved" else "DENIED",
                    "resolved_at": time.time()
                }
                if len(resolved_approvals) > 500:
                    try:
                        oldest = next(iter(resolved_approvals))
                        resolved_approvals.pop(oldest, None)
                    except Exception:
                        pass

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
        from core.tools.context import file_read_scope
        scope_token = file_read_scope.set(
            f"{team_id}:{agent_id}:{context.run_id}" if context and context.run_id else None)
        try:
            if asyncio.iscoroutinefunction(spec.handler):
                result = await spec.handler(arguments, team_id)
            else:
                result = spec.handler(arguments, team_id)
                if asyncio.iscoroutine(result):
                    result = await result

        except Exception as e:
            logger.exception("[Executor] Tool '%s' raised: %s", spec.name, e)
            return f"Error: Tool '{spec.name}' raised an exception: {type(e).__name__}: {e}"

        finally:
            file_read_scope.reset(scope_token)

        # If the tool returned a FileChangeResult, emit a file_change & file_system_updated event
        if isinstance(result, FileChangeResult):
            if not result.action or not result.path:
                return result.message
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
                "_seq": int(asyncio.get_event_loop().time() * 1000),
            }
            await event_bus.publish(f"team:{team_id}", event)
            if project_id:
                await event_bus.publish(f"project:{project_id}", event)
            await event_bus.publish("system:file_changes", event)

            fs_event = {
                "type": "file_system_updated",
                "action": result.action,
                "path": result.path,
                "paths": [result.path] if result.path else [],
                "project_id": project_id,
                "sender_id": agent_id,
                "sender_name": agent_name,
                "_seq": int(asyncio.get_event_loop().time() * 1000),
            }
            await event_bus.publish(f"team:{team_id}", fs_event)
            if project_id:
                await event_bus.publish(f"project:{project_id}", fs_event)
            await event_bus.publish("system:file_changes", fs_event)

            return result.message

        # Emit file_system_updated for file structure modification tools
        if spec.name in ("delete_file", "move_file", "copy_file", "create_directory") and isinstance(result, str) and not result.startswith("Error"):
            project_id = await _team_project_id(team_id)
            target_path = arguments.get("relative_path") or arguments.get("path") or arguments.get("destination") or arguments.get("source") or ""
            fs_event = {
                "type": "file_system_updated",
                "action": spec.name,
                "path": target_path,
                "paths": [target_path] if target_path else [],
                "project_id": project_id,
                "sender_id": agent_id,
                "sender_name": agent_name,
                "_seq": int(asyncio.get_event_loop().time() * 1000),
            }
            await event_bus.publish(f"team:{team_id}", fs_event)
            if project_id:
                await event_bus.publish(f"project:{project_id}", fs_event)
            await event_bus.publish("system:file_changes", fs_event)

            fc_event = {
                "type": "file_change",
                "action": spec.name,
                "path": target_path,
                "paths": [target_path] if target_path else [],
                "project_id": project_id,
                "sender_id": agent_id,
                "sender_name": agent_name,
                "diff": "",
                "_seq": int(asyncio.get_event_loop().time() * 1000),
            }
            await event_bus.publish(f"team:{team_id}", fc_event)
            if project_id:
                await event_bus.publish(f"project:{project_id}", fc_event)
            await event_bus.publish("system:file_changes", fc_event)

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
    force = bool(args.get("force", True))
    project_id = await _team_project_id(team_id)
    return await file_tools.read_file(path, project_id=project_id, team_id=team_id, force=force, start_line=args.get("start_line", 1), end_line=args.get("end_line"))

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
    return await file_tools.write_file(path, content, agent_name, project_id=project_id, team_id=team_id)

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
    return await file_tools.edit_file(path, target, replacement, agent_name, project_id=project_id, team_id=team_id)

async def _wrap_append_file(args: Dict[str, Any], team_id: str):
    path = args.get("relative_path") or args.get("path")
    content = args.get("content")
    agent_name = args.get("_agent_name", "Unknown")
    message_id = args.get("_active_message_id")
    if not path or content is None:
        return "Error: Missing parameters 'relative_path' or 'content' for append."
    try:
        await _check_active_editor_conflicts(path, agent_name)
    except Exception as e:
        return f"Error: {str(e)}"
    await _snapshot_file(path, team_id, message_id, operation="append_file")
    project_id = await _team_project_id(team_id)
    return await file_tools.append_file(path, content, agent_name, project_id=project_id, team_id=team_id)


async def _snapshot_file(relative_path: str, team_id: str, message_id: str | None, operation: str = "write_file"):
    """Save the current file content to FileBackup before it is modified.

    If the file does not exist (newly created), `backup_file_name` is saved as NULL.
    Saves snapshot whether or not a message_id is present so all modifications
    show up in Activity Log and File History.
    """
    if not team_id:
        return
    try:
        import uuid as _uuid
        import shutil
        import hashlib
        from pathlib import Path
        from core.memory.database import async_session
        from core.memory.models import FileBackup
        from core.tools.file_tools import file_tools as _ft

        project_id = await _team_project_id(team_id)
        resolved_path = await _ft._resolve_safe_path(relative_path, project_id=project_id)
        abs_path = str(resolved_path)
        p = Path(abs_path)
        
        async with async_session() as db:
            backup_file_name = None
            if p.exists() and p.is_file():
                path_hash = hashlib.sha256(abs_path.encode()).hexdigest()[:16]
                team_carole_dir = await _ft.get_team_carole_dir(team_id, db=db)
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

            msg_uuid = None
            if message_id:
                try:
                    msg_uuid = _uuid.UUID(message_id) if isinstance(message_id, str) else message_id
                except Exception:
                    msg_uuid = None

            backup = FileBackup(
                id=_uuid.uuid4(),
                team_id=_uuid.UUID(team_id) if isinstance(team_id, str) else team_id,
                message_id=msg_uuid,
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

    # Phase 5: Destructive Command Guardrails
    import re
    destructive_patterns = [
        r"\brm\s+-(?:[a-zA-Z]*[rf][a-zA-Z]*)\b",
        r"\bdrop\s+(?:table|database|schema)\b",
        r"\bgit\s+reset\s+--hard\b",
        r"\bgit\s+clean\s+-(?:[a-zA-Z]*f[a-zA-Z]*)\b",
        r"\btruncate\s+table\b",
    ]
    if any(re.search(pat, command, re.IGNORECASE) for pat in destructive_patterns):
        if not args.get("_server_approved") and not args.get("_human_confirmed"):
            return (
                f"⚠️ HIGH-RISK DESTRUCTIVE ACTION INTERCEPTED: '{command}'.\n"
                "This command contains destructive operations (rm -rf, DROP TABLE, git reset --hard) that risk irreversible data loss.\n"
                "To execute this command, you must obtain explicit human operator approval."
            )

    timeout = float(args.get("timeout", 60.0))
    background = bool(args.get("background", False) or args.get("is_daemon", False))
    context = args.get("_context")
    base_cwd = await _team_cwd(team_id)
    if not base_cwd:
        return "Error: Cannot resolve workspace directory for team."

    # Allow agent to specify a subdirectory relative to workspace root (Recommendation 7.E)
    # or an existing absolute directory on disk
    sub_cwd = args.get("cwd")
    if sub_cwd:
        from pathlib import Path
        raw = Path(sub_cwd)
        if raw.is_absolute():
            candidate = raw.resolve()
            if not candidate.is_dir():
                return f"Error: Specified cwd directory '{sub_cwd}' does not exist."
            cwd = str(candidate)
        else:
            root = Path(base_cwd).resolve()
            candidate = (root / sub_cwd).resolve()
            is_inside = False
            try:
                candidate.relative_to(root)
                is_inside = True
            except ValueError:
                if os.name == 'nt':
                    try:
                        Path(str(candidate).lower()).relative_to(Path(str(root).lower()))
                        is_inside = True
                    except ValueError:
                        is_inside = False
            if not is_inside:
                return f"Error: cwd '{sub_cwd}' escapes the workspace root."
            cwd = str(candidate)
    else:
        cwd = base_cwd
    return await shell_tools.execute_command(command, team_id, timeout, context=context, cwd=cwd, background=background)


async def _wrap_git_status(args: Dict[str, Any], team_id: str) -> str:
    cwd = await _team_cwd(team_id)
    if not cwd:
        return "Error: Cannot resolve workspace directory for team."
    return await git_tools.status(cwd=cwd)


async def _wrap_git_diff(args: Dict[str, Any], team_id: str) -> str:
    cwd = await _team_cwd(team_id)
    if not cwd:
        return "Error: Cannot resolve workspace directory for team."
    staged = args.get("staged", False)
    return await git_tools.diff(staged=staged, cwd=cwd)


async def _wrap_git_add(args: Dict[str, Any], team_id: str) -> str:
    cwd = await _team_cwd(team_id)
    if not cwd:
        return "Error: Cannot resolve workspace directory for team."
    paths = args.get("paths", ".") or args.get("value", ".")
    return await git_tools.add(paths, cwd=cwd)


async def _wrap_git_commit(args: Dict[str, Any], team_id: str) -> str:
    cwd = await _team_cwd(team_id)
    if not cwd:
        return "Error: Cannot resolve workspace directory for team."
    message = args.get("message") or args.get("value", "")
    return await git_tools.commit(message, cwd=cwd)


async def _wrap_git_log(args: Dict[str, Any], team_id: str) -> str:
    cwd = await _team_cwd(team_id)
    if not cwd:
        return "Error: Cannot resolve workspace directory for team."
    count = int(args.get("count", 10))
    return await git_tools.log(count=count, cwd=cwd)


async def _wrap_git_checkout(args: Dict[str, Any], team_id: str) -> str:
    cwd = await _team_cwd(team_id)
    if not cwd:
        return "Error: Cannot resolve workspace directory for team."
    branch = args.get("branch") or args.get("value", "")
    create = args.get("create", False)
    return await git_tools.checkout_branch(branch, create=create, cwd=cwd)


async def _wrap_git_push(args: Dict[str, Any], team_id: str) -> str:
    cwd = await _team_cwd(team_id)
    if not cwd:
        return "Error: Cannot resolve workspace directory for team."
    remote = args.get("remote", "origin")
    branch = args.get("branch")
    return await git_tools.push(remote, branch, cwd=cwd)


async def _wrap_git_pull(args: Dict[str, Any], team_id: str) -> str:
    cwd = await _team_cwd(team_id)
    if not cwd:
        return "Error: Cannot resolve workspace directory for team."
    remote = args.get("remote", "origin")
    branch = args.get("branch")
    return await git_tools.pull(remote, branch, cwd=cwd)


async def _wrap_git_branch(args: Dict[str, Any], team_id: str) -> str:
    cwd = await _team_cwd(team_id)
    if not cwd:
        return "Error: Cannot resolve workspace directory for team."
    show_all = args.get("all", False)
    return await git_tools.branch(all=show_all, cwd=cwd)


async def _wrap_web_search(args: Dict[str, Any], team_id: str) -> str:
    return await web_tools.web_search(
        query=args.get("query", ""),
        max_results=args.get("max_results", 5),
    )


async def _wrap_web_fetch(args: Dict[str, Any], team_id: str) -> str:
    return await web_tools.web_fetch(args.get("url", ""))


async def _wrap_web_extract_links(args: Dict[str, Any], team_id: str) -> str:
    return await web_tools.web_extract_links(
        url=args.get("url", ""),
        limit=args.get("limit", 50),
    )


async def _wrap_http_request(args: Dict[str, Any], team_id: str) -> str:
    return await web_tools.http_request(
        url=args.get("url", ""),
        method=args.get("method", "GET"),
        headers=args.get("headers"),
        body=args.get("body"),
        timeout=args.get("timeout", 30.0),
    )

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


# ── New: Snapshot / Act / Dialog wrappers ────────────────────────────────────

async def _wrap_browser_snapshot(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    include_screenshot = bool(args.get("include_screenshot", True))
    return await browser_tool.snapshot(agent_id, agent_name, team_id,
                                       include_screenshot=include_screenshot)


async def _wrap_browser_act(args: Dict[str, Any], team_id: str) -> str:
    kind = args.get("kind", "")
    if not kind:
        return "Error: Missing parameter 'kind'."
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    ref = args.get("ref")
    if ref is not None:
        try:
            ref = int(ref)
        except (ValueError, TypeError):
            ref = None
    selector = args.get("selector") or None
    text = args.get("text") or None
    key = args.get("key") or None
    value = args.get("value") or None
    x = args.get("x")
    y = args.get("y")
    frame_index = args.get("frame_index")
    if frame_index is not None:
        try:
            frame_index = int(frame_index)
        except (ValueError, TypeError):
            frame_index = None
    slow_type = bool(args.get("slow_type", False))
    return await browser_tool.act(
        kind, agent_id, agent_name, team_id,
        ref=ref, selector=selector, text=text, key=key,
        value=value, x=x, y=y, frame_index=frame_index,
        slow_type=slow_type,
    )


async def _wrap_browser_handle_dialog(args: Dict[str, Any], team_id: str) -> str:
    agent_id = args.get("_agent_id", "unknown")
    accept = bool(args.get("accept", True))
    prompt_text = args.get("prompt_text", "")
    return await browser_tool.handle_dialog(agent_id, accept=accept, prompt_text=prompt_text)


async def _wrap_browser_human_takeover(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.interaction_tools import interaction_tools
    from core.tools.browser_pool import browser_pool
    reason = args.get("reason") or args.get("question") or "Please complete the required manual browser action (CAPTCHA/2FA/Login)."
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")

    captcha_image = args.get("captcha_image") or args.get("captcha_image_base64")
    if not captcha_image:
        try:
            page = await browser_pool.get_page(agent_id)
            if page:
                import base64
                shot_bytes = await page.screenshot(type="jpeg", quality=65)
                captcha_image = base64.b64encode(shot_bytes).decode("utf-8")
        except Exception:
            pass

    return await interaction_tools.browser_human_takeover(
        reason=reason,
        agent_id=agent_id,
        agent_name=agent_name,
        team_id=team_id,
        captcha_image_base64=captcha_image,
    )


async def _wrap_spawn_agent(args: Dict[str, Any], team_id: str) -> str:
    calling_agent_name = args.get("_agent_name", "")
    if calling_agent_name.startswith("Subagent-") or calling_agent_name.startswith("Sub-"):
        return (
            "Error: Subagents cannot spawn further agents (max depth 1). "
            "Complete the task directly using your available tools."
        )

    pos = args.get("_positional_args", [])
    name = args.get("agent_name") or args.get("name") or ""
    task = args.get("task") or args.get("prompt", "")

    if pos:
        if len(pos) >= 1 and not name:
            name = str(pos[0])
        if len(pos) >= 2 and not task:
            task = str(pos[1])

    if not name and "value" in args:
        val_str = str(args["value"]).strip()
        parts = [p.strip().strip('"').strip("'") for p in re.findall(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'', val_str)]
        if len(parts) >= 1 and not name:
            name = parts[0]
        if len(parts) >= 2 and not task:
            task = parts[1]
        elif len(parts) == 0 and not name:
            name = val_str

    if not name or not task:
        return "Error: Missing 'agent_name' or 'task'."
    parent_id = args.get("_agent_id")
    parent_msg_id = args.get("_active_message_id")
    return await agent_tools.spawn_agent(name, task, team_id, parent_coordinator_id=parent_id, parent_message_id=parent_msg_id)

async def _wrap_hire_subagent(args: Dict[str, Any], team_id: str) -> str:
    agent_name = args.get("_agent_name", "")
    # Belt-and-suspenders depth guard (primary guard is 'subagents': 'block' in permissions)
    if agent_name.startswith("Subagent-") or agent_name.startswith("Sub-"):
        return (
            "Error: Subagents cannot hire further subagents (max depth 1). "
            "You are already a temporary specialist — complete the task yourself using "
            "the available file, shell, and web tools. Do NOT retry hire_subagent."
        )

    # Per-team concurrency cap: prevent cascade spawning (e.g. Archer hiring 5+ agents)
    # Count active subagent tasks whose name is associated with this team.
    # We use a simple global count cap — this avoids complex per-team tracking.
    _MAX_CONCURRENT_SUBAGENTS = 3
    active_count = sum(1 for t in _running_subagent_tasks if not t.done())
    if active_count >= _MAX_CONCURRENT_SUBAGENTS:
        return (
            f"Error: Too many subagents already running ({active_count}/{_MAX_CONCURRENT_SUBAGENTS}). "
            "Wait for existing subagents to complete before hiring more. "
            "Check for <task-notification> messages from running subagents."
        )
    
    pos = args.get("_positional_args", [])
    role = args.get("role", "")
    expertise = args.get("expertise", "")
    task = args.get("task", "")
    model = args.get("model")

    # Positional args support: hire_subagent("role", "task") or hire_subagent("role", "task", "constraints")
    if pos:
        if len(pos) == 1 and not task:
            task = str(pos[0])
        elif len(pos) == 2:
            if not role:
                role = str(pos[0])
            if not task:
                task = str(pos[1])
            if not expertise:
                expertise = f"Specialist in {role}"
        elif len(pos) >= 3:
            if not role:
                role = str(pos[0])
            # If 2nd argument looks like the task or expertise
            if not task:
                task = str(pos[1]) if len(str(pos[1])) > len(str(pos[2])) else f"{pos[1]}\n{pos[2]}"
            if not expertise:
                expertise = str(pos[2]) if str(pos[2]) != task else f"Specialist in {role}"

    # Fallback if raw 'value' string was provided
    if not task and "value" in args:
        val_str = str(args["value"]).strip()
        parts = [p.strip().strip('"').strip("'") for p in re.findall(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'', val_str)]
        if len(parts) >= 2:
            if not role:
                role = parts[0]
            if len(parts) == 2 and not task:
                task = parts[1]
                if not expertise:
                    expertise = f"Specialist in {role}"
            elif len(parts) >= 3:
                if not task:
                    task = parts[1] if len(parts[1]) > len(parts[2]) else f"{parts[1]}\n{parts[2]}"
                if not expertise:
                    expertise = parts[2] if parts[2] != task else f"Specialist in {role}"

    # Default expertise to role if not explicitly provided
    if role and task and not expertise:
        expertise = f"Specialist in {role}"

    if not role or not task:
        return "Error: Missing 'role' or 'task' for hire_subagent. Example: hire_subagent(role='Python Developer', expertise='Scripting', task='...')"
        
    agent_id = args.get("_agent_id", "")
    parent_msg_id = args.get("_active_message_id")
    return await agent_tools.hire_subagent(role, expertise, task, team_id, agent_id, model=model, parent_message_id=parent_msg_id)

async def _wrap_create_team_agent(args: Dict[str, Any], team_id: str) -> str:
    name = args.get("name") or args.get("agent_name") or ""
    role = args.get("role") or ""
    expertise = args.get("expertise") or args.get("custom_instructions") or ""
    system_prompt = args.get("system_prompt")
    model = args.get("model")
    personality = args.get("personality")
    agent_id = args.get("_agent_id", "")

    # Positional args fallback
    pos = args.get("_positional_args", [])
    if pos:
        if len(pos) >= 1 and not name:
            name = str(pos[0])
        if len(pos) >= 2 and not role:
            role = str(pos[1])
        if len(pos) >= 3 and not expertise:
            expertise = str(pos[2])

    if not name or not role:
        return "Error: Missing required parameters 'name' or 'role'. Usage: create_team_agent(name='Alex', role='Software Engineer', expertise='Full-stack Python & React development')"

    return await agent_tools.create_team_agent(
        name=name,
        role=role,
        expertise=expertise,
        system_prompt=system_prompt,
        model=model,
        personality=personality,
        team_id=team_id,
        _agent_id=agent_id
    )

async def _wrap_update_team_agent(args: Dict[str, Any], team_id: str) -> str:
    name_or_id = args.get("name_or_id") or args.get("name") or args.get("agent_name") or args.get("id", "")
    new_name = args.get("new_name")
    role = args.get("role")
    expertise = args.get("expertise") or args.get("specialization") or args.get("skills")
    model = args.get("model")
    personality = args.get("personality")
    custom_instructions = args.get("custom_instructions") or args.get("instructions")
    agent_id = args.get("_agent_id", "")

    if not name_or_id:
        return "Error: Missing required parameter 'name_or_id'. Usage: update_team_agent(name_or_id='Alex', role='Principal Software Engineer')"

    return await agent_tools.update_team_agent(
        name_or_id=name_or_id,
        new_name=new_name,
        role=role,
        expertise=expertise,
        model=model,
        personality=personality,
        custom_instructions=custom_instructions,
        team_id=team_id,
        _agent_id=agent_id
    )

async def _wrap_delete_team_agent(args: Dict[str, Any], team_id: str) -> str:
    name_or_id = args.get("name_or_id") or args.get("name") or args.get("agent_name") or args.get("id", "")
    agent_id = args.get("_agent_id", "")

    if not name_or_id:
        return "Error: Missing required parameter 'name_or_id'. Usage: delete_team_agent(name_or_id='Alex')"

    return await agent_tools.delete_team_agent(
        name_or_id=name_or_id,
        team_id=team_id,
        _agent_id=agent_id
    )

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
    depends_on = args.get("depends_on")
    target_files = args.get("target_files")
    contract_spec = args.get("contract_spec")
    verification_command = args.get("verification_command")
    agent_name = args.get("_agent_name")
    if not title:
        return "Error: Missing 'title'."
    return await task_tools.create_task(
        team_id=team_id,
        title=title,
        description=description,
        priority=priority,
        assignee_name=assignee,
        blocked_by_task_id=blocked_by_task_id,
        creator_agent_name=agent_name,
        target_files=target_files,
        contract_spec=contract_spec,
        verification_command=verification_command,
        depends_on=depends_on,
    )

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
    depends_on = args.get("depends_on")
    agent_name = args.get("_agent_name")
    if not task_id:
        return "Error: Missing 'task_id'."
    return await task_tools.update_task(
        task_id=task_id,
        status=status,
        notes=notes,
        assignee_name=assignee_name,
        agent_name=agent_name,
        blocked_by_task_id=blocked_by_task_id,
        team_id=team_id,
        depends_on=depends_on,
    )

async def _wrap_comment_on_task(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.task_tools import task_tools
    task_id = args.get("task_id", "")
    text = args.get("text", "")
    if not task_id or not text:
        return "Error: Missing 'task_id' or 'text'."
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")
    return await task_tools.comment_on_task(task_id, text, agent_id, agent_name, team_id=team_id)


async def _wrap_write_task_plan(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.task_tools import task_tools
    task_id = args.get("task_id", "").strip()
    plan_markdown = args.get("plan_markdown", "").strip()
    if not task_id or not plan_markdown:
        return "Error: Both 'task_id' and 'plan_markdown' are required."
    agent_id = args.get("_agent_id", "unknown")
    return await task_tools.write_task_plan(task_id, plan_markdown, agent_id, team_id)


async def _wrap_request_plan_approval(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.task_tools import task_tools
    task_id = args.get("task_id", "").strip()
    if not task_id:
        return "Error: 'task_id' is required."
    return await task_tools.request_plan_approval(task_id, team_id)


async def _wrap_update_task_todos(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.task_tools import task_tools
    task_id = args.get("task_id", "").strip()
    if not task_id:
        return "Error: 'task_id' is required."
    todos = args.get("todos")          # list or None
    toggle_id = args.get("toggle_id")  # str or None
    return await task_tools.update_task_todos(task_id, team_id, todos=todos, toggle_id=toggle_id)


# ---- Cron / Scheduled Task Wrappers ----

async def _wrap_create_scheduled_task(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.cron_task_tools import cron_task_tools
    name = args.get("name", "").strip()
    cron_expression = args.get("cron_expression", "").strip()
    prompt = args.get("prompt", "").strip()
    agent_id = args.get("_agent_id", "")
    if not name or not cron_expression or not prompt:
        return "Error: 'name', 'cron_expression', and 'prompt' are all required."
    return await cron_task_tools.create_scheduled_task(agent_id, team_id, name, cron_expression, prompt)

async def _wrap_list_scheduled_tasks(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.cron_task_tools import cron_task_tools
    return await cron_task_tools.list_scheduled_tasks(team_id)

async def _wrap_update_scheduled_task(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.cron_task_tools import cron_task_tools
    task_id = args.get("task_id", "").strip()
    if not task_id:
        return "Error: 'task_id' is required."
    return await cron_task_tools.update_scheduled_task(
        task_id=task_id,
        is_active=args.get("is_active"),
        cron_expression=args.get("cron_expression"),
        prompt=args.get("prompt"),
        name=args.get("name"),
    )

async def _wrap_delete_scheduled_task(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.cron_task_tools import cron_task_tools
    task_id = args.get("task_id", "").strip()
    if not task_id:
        return "Error: 'task_id' is required."
    return await cron_task_tools.delete_scheduled_task(task_id)


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
            "Usage: write_scratchpad(content=\"<the text you want to save>\", target='team')"
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
            "Usage: update_scratchpad(content=\"<the text you want to save>\", target='team')"
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
    questions = args.get("questions")
    options = args.get("options")  # optional list of choice strings
    agent_id = args.get("_agent_id", "unknown")
    agent_name = args.get("_agent_name", "Agent")

    # Handle stringified questions array
    if isinstance(questions, str) and questions.strip().startswith("[") and questions.strip().endswith("]"):
        import json
        try:
            questions = json.loads(questions.strip())
        except Exception:
            import ast
            try:
                questions = ast.literal_eval(questions.strip())
            except Exception:
                pass

    # Handle stringified JSON or JS objects passed in question/value
    if isinstance(question, str) and question.strip().startswith("{") and question.strip().endswith("}"):
        import json
        parsed = None
        try:
            parsed = json.loads(question.strip())
        except Exception:
            import ast
            try:
                parsed = ast.literal_eval(question.strip())
            except Exception:
                pass
        if isinstance(parsed, dict):
            question = parsed.get("question") or parsed.get("value") or question
            if "options" in parsed and isinstance(parsed["options"], list):
                options = parsed["options"]
            if "questions" in parsed and isinstance(parsed["questions"], list):
                questions = parsed["questions"]

    # Handle stringified list of options
    if isinstance(options, str) and options.strip().startswith("[") and options.strip().endswith("]"):
        import json
        try:
            options = json.loads(options.strip())
        except Exception:
            import ast
            try:
                options = ast.literal_eval(options.strip())
            except Exception:
                pass

    if not question and not questions:
        return "Error: Missing 'question' or 'questions'."

    parent_message_id = args.get("_active_message_id")

    return await interaction_tools.ask_user(
        question=str(question) if question else "",
        agent_id=agent_id,
        agent_name=agent_name,
        team_id=team_id,
        options=options,
        questions=questions,
        parent_message_id=parent_message_id,
    )


async def _wrap_fetch_tool_schemas(args: Dict[str, Any], team_id: str) -> str:
    """On-demand dynamic tool schema fetching / discovery."""
    family = (args.get("family") or args.get("category") or "").lower().strip()
    raw_names = args.get("tool_names") or args.get("tool_name") or []
    if isinstance(raw_names, str):
        tool_names = [raw_names]
    else:
        tool_names = list(raw_names)

    from core.tools.tool_registry import ToolRegistry
    activated = []
    for spec_name, spec in ToolRegistry._tools.items():
        matched = False
        if family and spec.category.lower() == family:
            matched = True
        elif spec_name in tool_names:
            matched = True
        if matched:
            param_list = ", ".join(spec.parameters.keys()) if spec.parameters else "none"
            activated.append(f"- **{spec.name}** ({spec.category}): {spec.description[:120]} (params: {param_list})")

    if not activated:
        available_families = sorted(list(set(s.category for s in ToolRegistry._tools.values())))
        return f"No tools found matching family '{family}' or tools '{tool_names}'. Available tool families: {', '.join(available_families)}"

    return f"Successfully discovered and activated {len(activated)} tools for this session:\n" + "\n".join(activated)


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
    src = args.get("source") or args.get("src") or ""
    dst = args.get("destination") or args.get("dst") or args.get("dest") or ""
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

async def _wrap_find_symbol_definition(args: Dict[str, Any], team_id: str) -> str:
    symbol_name = args.get("symbol_name") or args.get("name") or args.get("value", "")
    if not symbol_name:
        return "Error: Missing 'symbol_name'."
    project_id = await _team_project_id(team_id)
    return await code_analysis_tools.find_symbol_definition(symbol_name, project_id)

async def _wrap_get_file_outline(args: Dict[str, Any], team_id: str) -> str:
    file_path = args.get("file_path") or args.get("path") or args.get("value", "")
    if not file_path:
        return "Error: Missing 'file_path'."
    project_id = await _team_project_id(team_id)
    return await code_analysis_tools.get_file_outline(file_path, project_id)

async def _wrap_get_symbol_callers(args: Dict[str, Any], team_id: str) -> str:
    symbol_name = args.get("symbol_name") or args.get("name") or args.get("value", "")
    if not symbol_name:
        return "Error: Missing 'symbol_name'."
    project_id = await _team_project_id(team_id)
    return await code_analysis_tools.get_symbol_callers(symbol_name, project_id)

async def _wrap_get_symbol_callees(args: Dict[str, Any], team_id: str) -> str:
    function_name = args.get("function_name") or args.get("name") or args.get("value", "")
    file_path = args.get("file_path") or args.get("path", "")
    if not function_name:
        return "Error: Missing 'function_name'."
    if not file_path:
        return "Error: Missing 'file_path'."
    project_id = await _team_project_id(team_id)
    return await code_analysis_tools.get_symbol_callees(function_name, file_path, project_id)

async def _wrap_find_definitions(args: Dict[str, Any], team_id: str) -> str:
    symbol = args.get("symbol") or args.get("symbol_name") or args.get("name") or args.get("value", "")
    if not symbol:
        return "Error: Missing parameter 'symbol'."
    project_id = await _team_project_id(team_id)
    return await code_analysis_tools.find_definitions(symbol, project_id)

async def _wrap_find_callers(args: Dict[str, Any], team_id: str) -> str:
    function_name = args.get("function_name") or args.get("symbol") or args.get("name") or args.get("value", "")
    if not function_name:
        return "Error: Missing parameter 'function_name'."
    project_id = await _team_project_id(team_id)
    return await code_analysis_tools.find_callers(function_name, project_id)

async def _wrap_get_module_dependencies(args: Dict[str, Any], team_id: str) -> str:
    file_path = args.get("file_path") or args.get("path") or args.get("value", "")
    if not file_path:
        return "Error: Missing parameter 'file_path'."
    project_id = await _team_project_id(team_id)
    return await code_analysis_tools.get_module_dependencies(file_path, project_id)

async def _wrap_hybrid_code_search(args: Dict[str, Any], team_id: str) -> str:
    query = args.get("query") or args.get("value", "")
    if not query:
        return "Error: Missing parameter 'query'."
    top_k = int(args.get("top_k", 10))
    file_filter = args.get("file_filter") or args.get("file_path")
    kind = args.get("kind")
    from core.knowledge.hybrid_search import hybrid_code_search
    from core.knowledge.code_graph import code_graph
    project_id = await _team_project_id(team_id)

    # Lazily initialize project index from code_graph chunks only if empty
    p_idx = hybrid_code_search.get_project_index(project_id)
    if not p_idx.file_chunks:
        chunks = await code_graph.get_all_chunks(project_id)
        hybrid_code_search.index_workspace_chunks(chunks, project_id=project_id)

    results = await hybrid_code_search.search(
        query,
        project_id=project_id,
        top_k=top_k,
        file_filter=file_filter,
        kind=kind
    )
    if not results:
        return f"No code snippets found matching '{query}'."
    output = [f"Hybrid Search Results for '{query}':"]
    for r in results:
        bases_info = f" : {', '.join(r['bases'])}" if r.get('bases') else ""
        parent_info = f" (inside {r['parent_symbol']})" if r.get('parent_symbol') else ""
        output.append(f"\n[{r['file_path']} L{r['start_line']}-L{r['end_line']}] ({r['kind']}) {r['name']}{bases_info}{parent_info} (score: {r['score']})")
        output.append("```\n" + r['code'][:500] + ("\n..." if len(r['code']) > 500 else "") + "\n```")
    return "\n".join(output)

async def _wrap_get_class_hierarchy(args: Dict[str, Any], team_id: str) -> str:
    class_name = args.get("class_name", "")
    if not class_name:
        return "Error: Missing parameter 'class_name'."
    project_id = await _team_project_id(team_id)
    return await code_analysis_tools.get_class_hierarchy(class_name, project_id)

# ---- Memory Wrappers ----

async def _wrap_update_memory(args: Dict[str, Any], team_id: str) -> str:
    memory_id = args.get("memory_id", "")
    new_lesson = args.get("new_lesson", "")
    if not memory_id or not new_lesson:
        return "Error: Missing 'memory_id' or 'new_lesson'."
    return await memory_tools.update_memory(memory_id, new_lesson, team_id=team_id)

async def _wrap_forget_memory(args: Dict[str, Any], team_id: str) -> str:
    memory_id = args.get("memory_id", "")
    if not memory_id:
        return "Error: Missing 'memory_id'."
    return await memory_tools.forget_memory(memory_id, team_id=team_id)

async def _wrap_add_memory(args: Dict[str, Any], team_id: str) -> str:
    topic = args.get("topic", "")
    content = args.get("content", "")
    if not topic or not content:
        return "Error: Missing 'topic' or 'content'."
    # Resolve project_id from team_id for proper scoping
    from core.memory.database import async_session as _async_session
    from core.memory.models import Team as _Team
    from sqlalchemy import select as _select
    project_id = None
    try:
        async with _async_session() as db:
            t = (await db.execute(_select(_Team).where(_Team.id == _uuid_or_none(team_id)))).scalar_one_or_none()
            if t:
                project_id = str(t.project_id)
    except Exception:
        pass
    return await memory_tools.add_memory(
        topic=topic,
        content=content,
        team_id=team_id,
        project_id=project_id,
    )

async def _wrap_search_memory(args: Dict[str, Any], team_id: str) -> str:
    query = args.get("query", "")
    if not query:
        return "Error: Missing 'query'."
    limit = int(args.get("limit", 5))
    from core.memory.database import async_session as _async_session
    from core.memory.models import Team as _Team
    from sqlalchemy import select as _select
    project_id = None
    try:
        async with _async_session() as db:
            t = (await db.execute(_select(_Team).where(_Team.id == _uuid_or_none(team_id)))).scalar_one_or_none()
            if t:
                project_id = str(t.project_id)
    except Exception:
        pass
    return await memory_tools.search_memory(
        query=query,
        project_id=project_id,
        team_id=team_id,
        limit=limit,
    )

async def _wrap_add_fact(args: Dict[str, Any], team_id: str) -> str:
    key = args.get("key", "")
    value = args.get("value", "")
    if not key or not value:
        return "Error: Missing 'key' or 'value'."
    return await memory_tools.add_fact(key=key, value=value, team_id=team_id)

async def _wrap_edit_fact(args: Dict[str, Any], team_id: str) -> str:
    key = args.get("key", "")
    new_value = args.get("new_value", "")
    if not key or not new_value:
        return "Error: Missing 'key' or 'new_value'."
    return await memory_tools.edit_fact(key=key, new_value=new_value, team_id=team_id)

async def _wrap_delete_fact(args: Dict[str, Any], team_id: str) -> str:
    key = args.get("key", "")
    if not key:
        return "Error: Missing 'key'."
    return await memory_tools.delete_fact(key=key, team_id=team_id)

def _uuid_or_none(val):
    """Helper to safely parse a UUID string, returning None on failure."""
    try:
        import uuid as _uuid_mod
        return _uuid_mod.UUID(str(val))
    except Exception:
        return None

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



import tempfile
from pathlib import Path

async def _wrap_extract_document(args: Dict[str, Any], team_id: str) -> str:
    path_or_url = args.get("path_or_url", "")
    if not isinstance(path_or_url, str) or not path_or_url.strip():
        return "Error: Missing path_or_url parameter."

    path_or_url = path_or_url.strip()
    tmp_path = None
    is_remote = False

    try:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            is_remote = True
            try:
                result = await web_tools._fetch(path_or_url)
            except Exception as e:
                return f"Error downloading remote document: {e}"

            content = result.content
            ctype = result.mime_type or ""

            ext = ".txt"
            if "pdf" in ctype or path_or_url.lower().endswith(".pdf"):
                ext = ".pdf"
            elif "wordprocessingml.document" in ctype or path_or_url.lower().endswith(".docx"):
                ext = ".docx"
            elif "spreadsheetml.sheet" in ctype or path_or_url.lower().endswith(".xlsx"):
                ext = ".xlsx"
            elif "image" in ctype or any(path_or_url.lower().endswith(x) for x in [".jpg", ".jpeg", ".png", ".webp"]):
                ext = ".png"
            elif path_or_url.lower().endswith(".doc"):
                ext = ".doc"
            elif path_or_url.lower().endswith(".xls"):
                ext = ".xls"

            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
        else:
            base_dir = await _team_cwd(team_id)
            if not base_dir:
                return "Error: Cannot resolve workspace directory for team."

            root_dir = Path(base_dir).resolve()
            target_path = Path(path_or_url)
            if not target_path.is_absolute():
                target_path = (root_dir / target_path).resolve()
            else:
                target_path = target_path.resolve()

            is_inside = False
            try:
                target_path.relative_to(root_dir)
                is_inside = True
            except ValueError:
                if os.name == 'nt':
                    try:
                        Path(str(target_path).lower()).relative_to(Path(str(root_dir).lower()))
                        is_inside = True
                    except ValueError:
                        is_inside = False

            if not is_inside:
                return f"Error: Path '{path_or_url}' is outside workspace boundaries."

            if not target_path.exists() or not target_path.is_file():
                return f"Error: File '{path_or_url}' not found."

            tmp_path = str(target_path)

        def _parse_doc(file_path: str) -> tuple[str, str]:
            file_ext = os.path.splitext(file_path)[1].lower()
            text = ""
            if file_ext == ".pdf":
                try:
                    import PyPDF2
                    with open(file_path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        for page in reader.pages:
                            text += (page.extract_text() or "") + "\n"
                except ImportError:
                    return file_ext, "Error: PyPDF2 is not installed."
                except Exception as ex:
                    return file_ext, f"Error reading PDF: {ex}"
            elif file_ext == ".docx":
                try:
                    import docx
                    doc = docx.Document(file_path)
                    for para in doc.paragraphs:
                        text += para.text + "\n"
                except ImportError:
                    return file_ext, "Error: python-docx is not installed."
                except Exception as ex:
                    return file_ext, f"Error reading DOCX: {ex}"
            elif file_ext == ".xlsx":
                try:
                    import openpyxl
                    wb = openpyxl.load_workbook(file_path, data_only=True)
                    for sheet in wb.worksheets:
                        text += f"--- Sheet: {sheet.title} ---\n"
                        for row in sheet.iter_rows(values_only=True):
                            text += "\t".join([str(v) if v is not None else "" for v in row]) + "\n"
                except ImportError:
                    return file_ext, "Error: openpyxl is not installed."
                except Exception as ex:
                    return file_ext, f"Error reading XLSX: {ex}"
            elif file_ext in [".png", ".jpg", ".jpeg", ".webp"]:
                try:
                    import pytesseract
                    from PIL import Image
                    text = pytesseract.image_to_string(Image.open(file_path))
                except Exception as e:
                    return file_ext, f"Error extracting image text: {e}"
            else:
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read(100_000)
                except Exception as ex:
                    return file_ext, f"Error: Unsupported or unreadable document type: {file_ext} ({ex})"
            return file_ext, text

        doc_ext, parsed_text = await asyncio.to_thread(_parse_doc, tmp_path)
        if parsed_text.startswith("Error"):
            return parsed_text

        return f"Successfully extracted document ({doc_ext}):\n\n{parsed_text[:100000]}"

    except Exception as e:
        return f"Error processing document: {str(e)}"
    finally:
        if is_remote and tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass



async def _wrap_read_skill(args, team_id):
    from core.skills.skill_manager import SkillManager
    from core.memory.database import async_session
    project_id = await _team_project_id(team_id)
    if not project_id:
        return "Error: Skill access requires a valid team project"
    workspace = await file_tools.get_workspace_root(project_id)
    async with async_session() as db:
        skills = await SkillManager.discover_all_skills(workspace, team_id, db)
    for skill in skills:
        if skill.name == args.get("name") and skill.is_active:
            return f"Skill: {skill.name}\n{skill.instructions}"
    return "Error: Active skill not found in this scope"


async def _wrap_read_observation(args, team_id):
    from core.agent.observation_cache import read_observation
    agent_id = args.get("_agent_id")
    if not team_id or not agent_id:
        return "Error: Observation access requires a team and agent"
    try:
        return await asyncio.to_thread(read_observation, args.get("artifact_id", ""),
                                       f"{team_id}:{agent_id}", args.get("offset", 0), args.get("limit", 2500))
    except (OSError, ValueError, TypeError) as exc:
        return f"Error: Cannot read observation: {exc}"
