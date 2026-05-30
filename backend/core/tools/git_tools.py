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
from typing import Dict, Any


class GitTools:
    def __init__(self, workspace_root: str = None):
        if not workspace_root:
            workspace_root = os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[3]))
        self.workspace_root = Path(workspace_root).resolve()

    async def _run_git(self, *args: str) -> str:
        """Executes a git command inside the workspace and returns combined output."""
        cmd = ["git"] + list(args)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.workspace_root)
        )
        stdout, stderr = await process.communicate()
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")

        if process.returncode != 0:
            return f"Git Error (exit {process.returncode}):\n{err}\n{out}".strip()
        return out.strip()

    async def status(self) -> str:
        """Returns the current git status of the workspace."""
        return await self._run_git("status", "--short")

    async def diff(self, staged: bool = False) -> str:
        """Returns the diff of uncommitted changes. Use staged=True for staged changes."""
        if staged:
            return await self._run_git("diff", "--staged")
        return await self._run_git("diff")

    async def log(self, count: int = 10) -> str:
        """Returns the last N commit log entries."""
        return await self._run_git("log", f"--oneline", f"-{count}")

    async def add(self, paths: str = ".") -> str:
        """Stages files for commit. Defaults to staging all changes."""
        return await self._run_git("add", paths)

    async def commit(self, message: str) -> str:
        """Creates a commit with the given message."""
        if not message:
            return "Error: Commit message cannot be empty."
        return await self._run_git("commit", "-m", message)

    async def checkout_branch(self, branch_name: str, create: bool = False) -> str:
        """Checks out a branch. Use create=True to create a new branch."""
        if create:
            return await self._run_git("checkout", "-b", branch_name)
        return await self._run_git("checkout", branch_name)

    async def push(self, remote: str = "origin", branch: str = None) -> str:
        """Pushes the current branch to the remote."""
        if branch:
            return await self._run_git("push", remote, branch)
        return await self._run_git("push", remote, "HEAD")


# Singleton
git_tools = GitTools()
