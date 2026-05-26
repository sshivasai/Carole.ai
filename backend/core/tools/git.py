"""
Git operations: status, diff, commit, push, branch management
"""

import subprocess
from typing import Optional
from . import battlefield_tool


def _run_git(command: str, timeout: int = 30) -> tuple[str, int]:
    """Helper to run git commands"""
    result = subprocess.run(
        f"git {command}",
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout
    )
    output = result.stdout + result.stderr
    return output.strip(), result.returncode


@battlefield_tool(
    name="git_status",
    description="Get git repository status",
    category="git",
    parameters={}
)
def git_status() -> str:
    """Get git status"""
    try:
        output, code = _run_git("status")
        if code == 0:
            return f"✓ Git status:\n\n{output}"
        else:
            return f"✗ Git error:\n{output}"
    except Exception as e:
        return f"✗ Error running git status: {str(e)}"


@battlefield_tool(
    name="git_diff",
    description="Show git diff (unstaged changes)",
    category="git",
    parameters={
        "file": {"type": "string", "required": False, "description": "Specific file to diff"},
        "staged": {"type": "boolean", "required": False, "description": "Show staged changes (--cached)"}
    }
)
def git_diff(file: Optional[str] = None, staged: bool = False) -> str:
    """Show git diff"""
    try:
        cmd = "diff --cached" if staged else "diff"
        if file:
            cmd += f" {file}"

        output, code = _run_git(cmd)

        if not output:
            return "✓ No changes to show"

        return f"✓ Git diff:\n\n{output}"
    except Exception as e:
        return f"✗ Error running git diff: {str(e)}"


@battlefield_tool(
    name="git_log",
    description="Show git commit history",
    category="git",
    parameters={
        "count": {"type": "number", "required": False, "description": "Number of commits (default: 10)"},
        "oneline": {"type": "boolean", "required": False, "description": "Show one line per commit"}
    }
)
def git_log(count: int = 10, oneline: bool = True) -> str:
    """Show git log"""
    try:
        format_flag = "--oneline" if oneline else ""
        output, code = _run_git(f"log {format_flag} -n {count}")

        if code == 0:
            return f"✓ Last {count} commits:\n\n{output}"
        else:
            return f"✗ Git error:\n{output}"
    except Exception as e:
        return f"✗ Error running git log: {str(e)}"


@battlefield_tool(
    name="git_add",
    description="Stage files for commit",
    category="git",
    requires_confirmation=True,
    parameters={
        "files": {"type": "string", "required": True, "description": "Files to stage (space-separated or '.')"}
    }
)
def git_add(files: str) -> str:
    """Stage files"""
    try:
        output, code = _run_git(f"add {files}")

        if code == 0:
            return f"✓ Staged: {files}"
        else:
            return f"✗ Git add failed:\n{output}"
    except Exception as e:
        return f"✗ Error staging files: {str(e)}"


@battlefield_tool(
    name="git_commit",
    description="Create a git commit",
    category="git",
    requires_confirmation=True,
    parameters={
        "message": {"type": "string", "required": True, "description": "Commit message"}
    }
)
def git_commit(message: str) -> str:
    """Create commit"""
    try:
        # Escape quotes in message
        escaped_msg = message.replace('"', '\\"')
        output, code = _run_git(f'commit -m "{escaped_msg}"')

        if code == 0:
            return f"✓ Commit created:\n{output}"
        else:
            return f"✗ Commit failed:\n{output}"
    except Exception as e:
        return f"✗ Error committing: {str(e)}"


@battlefield_tool(
    name="git_push",
    description="Push commits to remote",
    category="git",
    requires_confirmation=True,
    parameters={
        "remote": {"type": "string", "required": False, "description": "Remote name (default: origin)"},
        "branch": {"type": "string", "required": False, "description": "Branch name (default: current)"}
    }
)
def git_push(remote: str = "origin", branch: Optional[str] = None) -> str:
    """Push to remote"""
    try:
        cmd = f"push {remote}"
        if branch:
            cmd += f" {branch}"

        output, code = _run_git(cmd, timeout=60)

        if code == 0:
            return f"✓ Pushed to {remote}:\n{output}"
        else:
            return f"✗ Push failed:\n{output}"
    except Exception as e:
        return f"✗ Error pushing: {str(e)}"


@battlefield_tool(
    name="git_branch",
    description="List, create, or switch branches",
    category="git",
    parameters={
        "action": {"type": "string", "required": False, "description": "Action: list, create, switch"},
        "branch_name": {"type": "string", "required": False, "description": "Branch name for create/switch"}
    }
)
def git_branch(action: str = "list", branch_name: Optional[str] = None) -> str:
    """Manage branches"""
    try:
        if action == "list":
            output, code = _run_git("branch -a")
            return f"✓ Branches:\n\n{output}" if code == 0 else f"✗ Error:\n{output}"

        elif action == "create":
            if not branch_name:
                return "✗ Branch name required for create action"
            output, code = _run_git(f"branch {branch_name}")
            return f"✓ Created branch: {branch_name}" if code == 0 else f"✗ Error:\n{output}"

        elif action == "switch":
            if not branch_name:
                return "✗ Branch name required for switch action"
            output, code = _run_git(f"checkout {branch_name}")
            return f"✓ Switched to: {branch_name}" if code == 0 else f"✗ Error:\n{output}"

        else:
            return f"✗ Unknown action: {action}"

    except Exception as e:
        return f"✗ Error managing branches: {str(e)}"


@battlefield_tool(
    name="git_clone",
    description="Clone a git repository",
    category="git",
    requires_confirmation=True,
    parameters={
        "url": {"type": "string", "required": True, "description": "Repository URL"},
        "directory": {"type": "string", "required": False, "description": "Target directory"}
    }
)
def git_clone(url: str, directory: Optional[str] = None) -> str:
    """Clone repository"""
    try:
        cmd = f"clone {url}"
        if directory:
            cmd += f" {directory}"

        output, code = _run_git(cmd, timeout=120)

        if code == 0:
            return f"✓ Cloned repository:\n{output}"
        else:
            return f"✗ Clone failed:\n{output}"
    except Exception as e:
        return f"✗ Error cloning: {str(e)}"


@battlefield_tool(
    name="git_stash",
    description="Stash uncommitted changes",
    category="git",
    parameters={
        "action": {"type": "string", "required": False, "description": "Action: save, pop, list (default: save)"},
        "message": {"type": "string", "required": False, "description": "Stash message"}
    }
)
def git_stash(action: str = "save", message: Optional[str] = None) -> str:
    """Manage stash"""
    try:
        if action == "save":
            cmd = "stash"
            if message:
                cmd += f' save "{message}"'
            output, code = _run_git(cmd)
            return f"✓ Changes stashed" if code == 0 else f"✗ Error:\n{output}"

        elif action == "pop":
            output, code = _run_git("stash pop")
            return f"✓ Stash applied and dropped" if code == 0 else f"✗ Error:\n{output}"

        elif action == "list":
            output, code = _run_git("stash list")
            return f"✓ Stashes:\n\n{output}" if output else "✓ No stashes"

        else:
            return f"✗ Unknown action: {action}"

    except Exception as e:
        return f"✗ Error managing stash: {str(e)}"
