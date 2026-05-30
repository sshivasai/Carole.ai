"""
# backend/core/tools/tool_executor.py

This module manages secure tool registration, permission gating, and human-in-the-loop approvals.

Permission Levels:
1. "safe" - Instantly executes.
2. "judge" - Pauses and requests an async verification appraisal from the team's Judge AI.
3. "human" - Pauses and blocks the execution flow, emitting a WebSocket event to the UI,
            blocking until the human approves or denies the transaction.
"""

import uuid
import asyncio
from typing import Dict, Any, Callable, Awaitable

from core.chat.event_bus import event_bus
from core.tools.file_tools import file_tools
from core.tools.shell_tools import shell_tools
from core.tools.git_tools import git_tools
from core.tools.web_tools import web_tools

# Global dictionaries to manage pending human approvals across concurrent agent loops
pending_approvals: Dict[str, asyncio.Event] = {}
approval_results: Dict[str, bool] = {}  # Maps tx_id to True (Approved) or False (Denied)


class ToolExecutor:
    def __init__(self):
        # Register mapping of tool names to their operational functions
        self.registry: Dict[str, Callable[..., Awaitable[str]]] = {
            # File system tools
            "read_file": self._wrap_read_file,
            "write_file": self._wrap_write_file,
            "edit_file": self._wrap_edit_file,
            "list_directory": self._wrap_list_directory,
            # Shell tools
            "execute_command": self._wrap_execute_command,
            # Git tools
            "git_status": self._wrap_git_status,
            "git_diff": self._wrap_git_diff,
            "git_add": self._wrap_git_add,
            "git_commit": self._wrap_git_commit,
            "git_log": self._wrap_git_log,
            "git_checkout": self._wrap_git_checkout,
            "git_push": self._wrap_git_push,
            # Web research tools
            "web_search": self._wrap_web_search,
            "web_fetch": self._wrap_web_fetch,
        }

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
        if tool_name not in self.registry:
            return f"Error: Tool '{tool_name}' is not registered in the system."

        # Fetch the permission level for this specific tool (defaults to "human" for security)
        gate_level = permissions.get(tool_name, "human")

        # 1. Safe — instant execution
        if gate_level == "safe":
            return await self.registry[tool_name](arguments, team_id)

        # 2. Judge — broadcast review request, then execute
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
            # TODO: Hook actual Judge LLM prompt evaluation here
            print(f"⚖️ [Judge] Appraising tool '{tool_name}' for agent '{agent_name}'...")
            await asyncio.sleep(1.0)
            return await self.registry[tool_name](arguments, team_id)

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
                return await self.registry[tool_name](arguments, team_id)
            else:
                print(f"✗ [Executor] Tx {tx_id} DENIED. Cancelling execution...")
                return f"✗ Execution Cancelled: Human operator denied approval to run '{tool_name}'."

        else:
            return f"Error: Unknown tool permission gate level '{gate_level}'."

    # ========================
    # File System Wrappers
    # ========================

    async def _wrap_read_file(self, args: Dict[str, Any], team_id: str) -> str:
        path = args.get("relative_path") or args.get("path") or args.get("value")
        if not path:
            return "Error: Missing parameter 'relative_path'."
        return file_tools.read_file(path)

    async def _wrap_write_file(self, args: Dict[str, Any], team_id: str) -> str:
        path = args.get("relative_path") or args.get("path")
        content = args.get("content")
        if not path or content is None:
            return "Error: Missing parameter 'relative_path' or 'content'."
        return file_tools.write_file(path, content)

    async def _wrap_edit_file(self, args: Dict[str, Any], team_id: str) -> str:
        path = args.get("relative_path") or args.get("path")
        target = args.get("target_content") or args.get("target")
        replacement = args.get("replacement_content") or args.get("replacement")
        if not path or target is None or replacement is None:
            return "Error: Missing parameters for editing."
        return file_tools.edit_file(path, target, replacement)

    async def _wrap_list_directory(self, args: Dict[str, Any], team_id: str) -> str:
        path = args.get("relative_path", ".") or args.get("path", ".")
        return file_tools.list_directory(path)

    # ========================
    # Shell Wrappers
    # ========================

    async def _wrap_execute_command(self, args: Dict[str, Any], team_id: str) -> str:
        command = args.get("command") or args.get("value")
        if not command:
            return "Error: Missing parameter 'command'."
        timeout = float(args.get("timeout", 60.0))
        return await shell_tools.execute_command(command, team_id, timeout)

    # ========================
    # Git Wrappers
    # ========================

    async def _wrap_git_status(self, args: Dict[str, Any], team_id: str) -> str:
        return await git_tools.status()

    async def _wrap_git_diff(self, args: Dict[str, Any], team_id: str) -> str:
        staged = args.get("staged", False)
        return await git_tools.diff(staged=staged)

    async def _wrap_git_add(self, args: Dict[str, Any], team_id: str) -> str:
        paths = args.get("paths", ".") or args.get("value", ".")
        return await git_tools.add(paths)

    async def _wrap_git_commit(self, args: Dict[str, Any], team_id: str) -> str:
        message = args.get("message") or args.get("value", "")
        return await git_tools.commit(message)

    async def _wrap_git_log(self, args: Dict[str, Any], team_id: str) -> str:
        count = int(args.get("count", 10))
        return await git_tools.log(count=count)

    async def _wrap_git_checkout(self, args: Dict[str, Any], team_id: str) -> str:
        branch = args.get("branch") or args.get("value", "")
        create = args.get("create", False)
        return await git_tools.checkout_branch(branch, create=create)

    async def _wrap_git_push(self, args: Dict[str, Any], team_id: str) -> str:
        remote = args.get("remote", "origin")
        branch = args.get("branch")
        return await git_tools.push(remote, branch)

    # ========================
    # Web Research Wrappers
    # ========================

    async def _wrap_web_search(self, args: Dict[str, Any], team_id: str) -> str:
        query = args.get("query") or args.get("value", "")
        if not query:
            return "Error: Missing parameter 'query'."
        max_results = int(args.get("max_results", 5))
        return await web_tools.web_search(query, max_results)

    async def _wrap_web_fetch(self, args: Dict[str, Any], team_id: str) -> str:
        url = args.get("url") or args.get("value", "")
        if not url:
            return "Error: Missing parameter 'url'."
        return await web_tools.web_fetch(url)


# Singleton global executor
tool_executor = ToolExecutor()
