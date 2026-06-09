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
from typing import Dict, Any, Callable, Awaitable

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

# Global dictionaries to manage pending human approvals across concurrent agent loops
pending_approvals: Dict[str, asyncio.Event] = {}
approval_results: Dict[str, bool] = {}  # Maps tx_id to True (Approved) or False (Denied)


def register_builtin_tools():
    """Registers all built-in tools with the ToolRegistry at startup.
    Called once from main.py lifespan."""

    builtins = [
        # ---- Filesystem ----
        ToolSpec("read_file", "Read contents of a file", "filesystem",
                 {"relative_path": {"type": "string", "required": True}},
                 "safe", _wrap_read_file),
        ToolSpec("write_file", "Create or overwrite a file", "filesystem",
                 {"relative_path": {"type": "string", "required": True},
                  "content": {"type": "string", "required": True}},
                 "judge", _wrap_write_file),
        ToolSpec("edit_file", "Replace a specific block of text in a file", "filesystem",
                 {"relative_path": {"type": "string", "required": True},
                  "target_content": {"type": "string", "required": True},
                  "replacement_content": {"type": "string", "required": True}},
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
        ToolSpec("execute_command", "Execute a shell command in the workspace", "shell",
                 {"command": {"type": "string", "required": True},
                  "timeout": {"type": "number", "required": False}},
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
        ToolSpec("web_search", "Search the web for information", "web",
                 {"query": {"type": "string", "required": True},
                  "max_results": {"type": "number", "required": False}},
                 "safe", _wrap_web_search),
        ToolSpec("web_fetch", "Fetch and extract text from a URL", "web",
                 {"url": {"type": "string", "required": True}}, "safe", _wrap_web_fetch),

        # ---- Browser Automation ----
        ToolSpec("browser_navigate", "Navigate to a URL, take screenshot, return page title+text", "browser",
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
        ToolSpec("browser_type", "Type text into an input element (clears existing content)", "browser",
                 {"selector": {"type": "string", "required": True},
                  "text": {"type": "string", "required": True},
                  "clear_first": {"type": "boolean", "required": False}},
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

        # ---- Coordination ----
        ToolSpec("spawn_agent", "Spawn a teammate's ReACT loop with a task", "coordination",
                 {"agent_name": {"type": "string", "required": True},
                  "task": {"type": "string", "required": True}},
                 "safe", _wrap_spawn_agent),
        ToolSpec("hire_subagent", "Dynamically hire a temporary subagent to offload a specific task", "coordination",
                 {"role": {"type": "string", "required": True},
                  "expertise": {"type": "string", "required": True},
                  "task": {"type": "string", "required": True},
                  "model": {"type": "string", "required": False}},
                 "judge", _wrap_hire_subagent),
        ToolSpec("send_message", "Send a message in the team chat", "coordination",
                 {"text": {"type": "string", "required": True},
                  "recipient_name": {"type": "string", "required": False}},
                 "safe", _wrap_send_message),

        # ---- Tasks ----
        ToolSpec("create_task", "Create a task on the team board", "task",
                 {"title": {"type": "string", "required": True},
                  "description": {"type": "string", "required": False},
                  "priority": {"type": "string", "required": False},
                  "assignee": {"type": "string", "required": False}},
                 "safe", _wrap_create_task),
        ToolSpec("list_tasks", "List tasks on the team board", "task",
                 {"status": {"type": "string", "required": False}},
                 "safe", _wrap_list_tasks),
        ToolSpec("update_task", "Update a task's status", "task",
                 {"task_id": {"type": "string", "required": True},
                  "status": {"type": "string", "required": False},
                  "notes": {"type": "string", "required": False}},
                 "safe", _wrap_update_task),

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
    ]

    for spec in builtins:
        ToolRegistry.register(spec)

    print(f"🔧 [ToolRegistry] Registered {len(builtins)} built-in tools.")


class ToolExecutor:
    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_id: str,
        agent_name: str,
        team_id: str,
        permissions: Dict[str, str]
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

        # 1. Safe — instant execution
        if gate_level == "safe":
            return await self._run_tool(spec, arguments, agent_id, agent_name, team_id)

        # 2. Judge — LLM-based review, then execute
        elif gate_level == "judge":
            topic = f"team:{team_id}"
            await event_bus.publish(topic, {
                "type": "judge_review_request",
                "agent_id": agent_id,
                "agent_name": agent_name,
                "tool_name": tool_name,
                "arguments": arguments,
                "text": f"⚠️ Agent '{agent_name}' wants to run '{tool_name}'. Awaiting Judge AI appraisal..."
            })
            approved = await judge_evaluator.evaluate(tool_name, arguments, agent_name)
            if approved:
                return await self._run_tool(spec, arguments, agent_id, agent_name, team_id)
            else:
                return f"✗ Judge DENIED execution of '{tool_name}' for agent '{agent_name}'."

        # 3. Human — block until user approves via POST /api/tools/approve/{tx_id}
        elif gate_level == "human":
            tx_id = str(uuid.uuid4())
            topic = f"team:{team_id}"

            event = asyncio.Event()
            pending_approvals[tx_id] = event

            await event_bus.publish(topic, {
                "type": "approval_request",
                "tx_id": tx_id,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "tool_name": tool_name,
                "arguments": arguments,
                "text": f"🛑 Approval Required: Agent '{agent_name}' wants to execute '{tool_name}'."
            })

            print(f"🛑 [Executor] Pausing agent '{agent_name}' loop. Awaiting human approval for Tx: {tx_id}...")
            await event.wait()

            approved = approval_results.pop(tx_id, False)
            pending_approvals.pop(tx_id, None)

            if approved:
                print(f"✓ [Executor] Tx {tx_id} APPROVED. Resuming execution...")
                return await self._run_tool(spec, arguments, agent_id, agent_name, team_id)
            else:
                print(f"✗ [Executor] Tx {tx_id} DENIED. Cancelling execution...")
                return f"✗ Execution Cancelled: Human operator denied approval to run '{tool_name}'."

        else:
            return f"Error: Unknown tool permission gate level '{gate_level}'."

    async def _run_tool(
        self, spec: ToolSpec, arguments: Dict[str, Any],
        agent_id: str, agent_name: str, team_id: str
    ) -> str:
        """Executes the tool handler and emits file_change events for file operations."""
        # Inject agent identity into args so tool wrappers can access it
        arguments["_agent_id"] = agent_id
        arguments["_agent_name"] = agent_name
        result = await spec.handler(arguments, team_id)

        # If the tool returned a FileChangeResult, emit a file_change event
        if isinstance(result, FileChangeResult):
            if result.diff:
                event = {
                    "type": "file_change",
                    "action": result.action,
                    "path": result.path,
                    "diff": result.diff,
                    "before_content": result.before_content,
                    "after_content": result.after_content,
                    "sender_id": agent_id,
                    "sender_name": agent_name,
                }
                await event_bus.publish(f"team:{team_id}", event)
                await event_bus.publish("system:file_changes", event)
            return result.message

        return result


# ========================
# Tool Handler Functions
# ========================

async def _wrap_read_file(args: Dict[str, Any], team_id: str) -> str:
    path = args.get("relative_path") or args.get("path") or args.get("value")
    if not path:
        return "Error: Missing parameter 'relative_path'."
    return await file_tools.read_file(path)

async def _wrap_write_file(args: Dict[str, Any], team_id: str):
    path = args.get("relative_path") or args.get("path")
    content = args.get("content")
    agent_name = args.get("_agent_name", "Unknown")
    if not path or content is None:
        return "Error: Missing parameter 'relative_path' or 'content'."
    return await file_tools.write_file(path, content, agent_name)

async def _wrap_edit_file(args: Dict[str, Any], team_id: str):
    path = args.get("relative_path") or args.get("path")
    target = args.get("target_content") or args.get("target")
    replacement = args.get("replacement_content") or args.get("replacement")
    agent_name = args.get("_agent_name", "Unknown")
    if not path or target is None or replacement is None:
        return "Error: Missing parameters for editing."
    return await file_tools.edit_file(path, target, replacement, agent_name)

async def _wrap_list_directory(args: Dict[str, Any], team_id: str) -> str:
    path = args.get("relative_path", ".") or args.get("path", ".")
    return await file_tools.list_directory(path)

async def _wrap_execute_command(args: Dict[str, Any], team_id: str) -> str:
    command = args.get("command") or args.get("value")
    if not command:
        return "Error: Missing parameter 'command'."
    timeout = float(args.get("timeout", 60.0))
    return await shell_tools.execute_command(command, team_id, timeout)

async def _wrap_git_status(args: Dict[str, Any], team_id: str) -> str:
    return await git_tools.status()

async def _wrap_git_diff(args: Dict[str, Any], team_id: str) -> str:
    staged = args.get("staged", False)
    return await git_tools.diff(staged=staged)

async def _wrap_git_add(args: Dict[str, Any], team_id: str) -> str:
    paths = args.get("paths", ".") or args.get("value", ".")
    return await git_tools.add(paths)

async def _wrap_git_commit(args: Dict[str, Any], team_id: str) -> str:
    message = args.get("message") or args.get("value", "")
    return await git_tools.commit(message)

async def _wrap_git_log(args: Dict[str, Any], team_id: str) -> str:
    count = int(args.get("count", 10))
    return await git_tools.log(count=count)

async def _wrap_git_checkout(args: Dict[str, Any], team_id: str) -> str:
    branch = args.get("branch") or args.get("value", "")
    create = args.get("create", False)
    return await git_tools.checkout_branch(branch, create=create)

async def _wrap_git_push(args: Dict[str, Any], team_id: str) -> str:
    remote = args.get("remote", "origin")
    branch = args.get("branch")
    return await git_tools.push(remote, branch)

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


async def _wrap_spawn_agent(args: Dict[str, Any], team_id: str) -> str:
    name = args.get("agent_name") or args.get("name") or args.get("value", "")
    task = args.get("task") or args.get("prompt", "")
    if not name or not task:
        return "Error: Missing 'agent_name' or 'task'."
    parent_id = args.get("_agent_id")
    return await agent_tools.spawn_agent(name, task, team_id, parent_coordinator_id=parent_id)

async def _wrap_hire_subagent(args: Dict[str, Any], team_id: str) -> str:
    agent_name = args.get("_agent_name", "")
    # Enforce 1-Level Only Guardrail
    if agent_name.startswith("Subagent-"):
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
    sender = args.get("sender_id", "agent")
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
    if not title:
        return "Error: Missing 'title'."
    return await task_tools.create_task(team_id, title, description, priority, assignee)

async def _wrap_list_tasks(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.task_tools import task_tools
    status = args.get("status")
    return await task_tools.list_tasks(team_id, status)

async def _wrap_update_task(args: Dict[str, Any], team_id: str) -> str:
    from core.tools.task_tools import task_tools
    task_id = args.get("task_id", "")
    status = args.get("status")
    notes = args.get("notes")
    if not task_id:
        return "Error: Missing 'task_id'."
    return await task_tools.update_task(task_id, status, notes)


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
    return await file_tools.append_file(path, content, agent_name)


async def _wrap_delete_file(args: Dict[str, Any], team_id: str) -> str:
    path = args.get("relative_path") or args.get("path") or args.get("value")
    agent_name = args.get("_agent_name", "Unknown")
    if not path:
        return "Error: Missing 'relative_path'."
    return await file_tools.delete_file(path, agent_name)


async def _wrap_grep_search(args: Dict[str, Any], team_id: str) -> str:
    pattern = args.get("pattern") or args.get("value", "")
    if not pattern:
        return "Error: Missing 'pattern'."
    path = args.get("path", ".")
    case_sensitive = args.get("case_sensitive", True)
    return await file_tools.grep_search(pattern, path, case_sensitive)


async def _wrap_glob_search(args: Dict[str, Any], team_id: str) -> str:
    pattern = args.get("pattern") or args.get("value", "")
    if not pattern:
        return "Error: Missing 'pattern'."
    path = args.get("path", ".")
    return await file_tools.glob_search(pattern, path)


# Singleton global executor
tool_executor = ToolExecutor()


# ---- New Filesystem Wrappers ----

async def _wrap_copy_file(args: Dict[str, Any], team_id: str) -> str:
    src = args.get("source", "")
    dst = args.get("destination", "")
    if not src or not dst:
        return "Error: Missing 'source' or 'destination'."
    return await file_tools.copy_file(src, dst)

async def _wrap_move_file(args: Dict[str, Any], team_id: str) -> str:
    src = args.get("source", "")
    dst = args.get("destination", "")
    if not src or not dst:
        return "Error: Missing 'source' or 'destination'."
    return await file_tools.move_file(src, dst)

async def _wrap_create_directory(args: Dict[str, Any], team_id: str) -> str:
    path = args.get("path") or args.get("relative_path", "")
    if not path:
        return "Error: Missing 'path'."
    return await file_tools.create_directory(path)


# ---- Git Extras ----

async def _wrap_git_stash(args: Dict[str, Any], team_id: str) -> str:
    action = args.get("action", "push")
    message = args.get("message")
    return await git_tools.stash(action, message)

async def _wrap_git_clone(args: Dict[str, Any], team_id: str) -> str:
    url = args.get("url", "")
    if not url:
        return "Error: Missing 'url'."
    directory = args.get("directory")
    return await git_tools.clone(url, directory)


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
    return code_analysis_tools.analyze_impact(path)

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
    return create_meeting(summary, start_time_iso, end_time_iso, attendees_emails)

async def _wrap_send_email(args: Dict[str, Any], team_id: str) -> str:
    to_email = args.get("to_email", "")
    subject = args.get("subject", "")
    body = args.get("body", "")
    if not to_email or not subject or not body:
        return "Error: Missing 'to_email', 'subject', or 'body'."
    return send_email(to_email, subject, body)

async def _wrap_generate_mom(args: Dict[str, Any], team_id: str) -> str:
    transcription = args.get("transcription", "")
    if not transcription:
        return "Error: Missing 'transcription'."
    return await meeting_tool.generate_mom(transcription)

