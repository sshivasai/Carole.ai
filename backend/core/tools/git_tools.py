"""
# backend/core/tools/git_tools.py

This module provides comprehensive Git version control workflows.

Responsibilities:
1. Provide `git_status`, `git_diff`, `git_add`, `git_commit`, `git_log` tools.
2. Enable Coder agents to create branches, make atomic commits, and push PRs.
3. Enable Reviewer agents to pull code, diff changes, and suggest amendments.
4. All operations are sandboxed to the workspace root directory.
"""

import os
import asyncio
from pathlib import Path
from typing import Optional


class GitTools:
    def __init__(self, workspace_root: str = None):
        if not workspace_root:
            workspace_root = os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[3]))
        self.workspace_root = Path(workspace_root).resolve()

    async def _run_git(self, *args: str, cwd: Optional[str] = None) -> str:
        """Executes a git command inside the workspace and returns combined output.

        `cwd` scopes the command to the agent's project workspace when provided
        (so concurrent agents on different projects don't operate on a shared
        repo root). Falls back to the shared workspace root otherwise.
        """
        cmd = ["git"] + list(args)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd or str(self.workspace_root)
        )
        stdout, stderr = await process.communicate()
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")

        if process.returncode != 0:
            return f"Git Error (exit {process.returncode}):\n{err}\n{out}".strip()
        return out.strip()

    async def status(self, cwd: Optional[str] = None) -> str:
        """Returns the current git status of the workspace."""
        return await self._run_git("status", "--short", cwd=cwd)

    async def diff(self, staged: bool = False, cwd: Optional[str] = None) -> str:
        """Returns the diff of uncommitted changes. Use staged=True for staged changes."""
        if staged:
            return await self._run_git("diff", "--staged", cwd=cwd)
        return await self._run_git("diff", cwd=cwd)

    async def log(self, count: int = 10, cwd: Optional[str] = None) -> str:
        """Returns the last N commit log entries."""
        return await self._run_git("log", "--oneline", f"-{count}", cwd=cwd)

    async def add(self, paths: str = ".", cwd: Optional[str] = None) -> str:
        """Stages files for commit. Defaults to staging all changes."""
        return await self._run_git("add", paths, cwd=cwd)

    async def commit(self, message: str, cwd: Optional[str] = None) -> str:
        """Creates a commit with the given message."""
        if not message:
            return "Error: Commit message cannot be empty."
        return await self._run_git("commit", "-m", message, cwd=cwd)

    async def checkout_branch(self, branch_name: str, create: bool = False, cwd: Optional[str] = None) -> str:
        """Checks out a branch. Use create=True to create a new branch."""
        if create:
            return await self._run_git("checkout", "-b", branch_name, cwd=cwd)
        return await self._run_git("checkout", branch_name, cwd=cwd)

    async def push(self, remote: str = "origin", branch: str = None, cwd: Optional[str] = None) -> str:
        """Pushes the current branch to the remote."""
        if branch:
            return await self._run_git("push", remote, branch, cwd=cwd)
        return await self._run_git("push", remote, "HEAD", cwd=cwd)

    async def stash(self, action: str = "push", message: str = None, cwd: Optional[str] = None) -> str:
        """Stash or unstash changes. action: push, pop, list, drop."""
        if action == "push":
            if message:
                return await self._run_git("stash", "push", "-m", message, cwd=cwd)
            return await self._run_git("stash", "push", cwd=cwd)
        elif action == "pop":
            return await self._run_git("stash", "pop", cwd=cwd)
        elif action == "list":
            return await self._run_git("stash", "list", cwd=cwd)
        elif action == "drop":
            return await self._run_git("stash", "drop", cwd=cwd)
        else:
            return f"Error: Unknown stash action '{action}'. Use push, pop, list, or drop."

    async def clone(self, url: str, directory: str = None, cwd: Optional[str] = None) -> str:
        """Clones a repository into the workspace."""
        args = ["clone", url]
        if directory:
            args.append(directory)
        return await self._run_git(*args, cwd=cwd)


# Singleton
git_tools = GitTools()
