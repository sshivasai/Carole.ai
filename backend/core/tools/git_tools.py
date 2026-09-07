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


import urllib.parse
import ipaddress
import re


def _validate_git_url(url: str) -> Optional[str]:
    """Validates git clone URL to allow safe development while preventing cloud metadata attacks."""
    url_str = (url or "").strip()
    if not url_str:
        return "Error: Git URL cannot be empty."

    # Allow standard SSH git syntax: git@github.com:user/repo.git
    if re.match(r"^git@[a-zA-Z0-9.\-]+:[a-zA-Z0-9_\-/\.]+(\.git)?$", url_str):
        return None

    from core.tools.ssrf_guard import assert_safe_public_url
    try:
        assert_safe_public_url(url_str, allow_local=True)
    except ValueError as e:
        return f"Error: {e}"

    return None


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
        val_err = _validate_git_url(url)
        if val_err:
            return val_err
        base_dir = Path(cwd).resolve() if cwd else self.workspace_root.resolve()
        args = ["clone", url]
        if directory:
            target_dir = Path(directory)
            if not target_dir.is_absolute():
                resolved_target = (base_dir / target_dir).resolve()
            else:
                resolved_target = target_dir.resolve()
            is_inside = False
            try:
                resolved_target.relative_to(base_dir)
                is_inside = True
            except ValueError:
                if os.name == 'nt':
                    try:
                        Path(str(resolved_target).lower()).relative_to(Path(str(base_dir).lower()))
                        is_inside = True
                    except ValueError:
                        is_inside = False
            if not is_inside:
                return f"Error: Clone destination directory '{directory}' escapes workspace sandbox."
            args.append(str(resolved_target))
        return await self._run_git(*args, cwd=str(base_dir))

    async def pull(self, remote: str = "origin", branch: str = None, cwd: Optional[str] = None) -> str:
        """Pulls latest changes from the remote. Equivalent to git fetch + git merge."""
        if branch:
            return await self._run_git("pull", remote, branch, cwd=cwd)
        return await self._run_git("pull", remote, cwd=cwd)

    async def branch(self, all: bool = False, cwd: Optional[str] = None) -> str:
        """Lists branches. all=True includes remote-tracking branches."""
        if all:
            return await self._run_git("branch", "-a", cwd=cwd)
        return await self._run_git("branch", "-v", cwd=cwd)

    async def create_checkpoint(self, name: str = "", cwd: Optional[str] = None) -> dict:
        """
        Creates an atomic Git checkpoint in refs/carole/checkpoints/<checkpoint_id>.
        Stages current changes and commits if dirty, then records the reference.
        """
        import time
        import secrets

        checkpoint_id = f"cp_{int(time.time())}_{secrets.token_hex(4)}"
        status = await self.status(cwd=cwd)
        if "Git Error" in status and "not a git repository" in status.lower():
            await self._run_git("init", cwd=cwd)

        await self._run_git("add", "-A", cwd=cwd)
        diff_staged = await self._run_git("diff", "--staged", cwd=cwd)
        commit_msg = f"[CAROLE CHECKPOINT] {name or 'Manual Checkpoint'}"
        if diff_staged:
            await self._run_git("commit", "-m", commit_msg, cwd=cwd)
        else:
            head_check = await self._run_git("rev-parse", "--verify", "HEAD", cwd=cwd)
            if "Git Error" in head_check:
                await self._run_git("commit", "--allow-empty", "-m", commit_msg, cwd=cwd)

        head_sha = await self._run_git("rev-parse", "HEAD", cwd=cwd)
        ref_name = f"refs/carole/checkpoints/{checkpoint_id}"
        await self._run_git("update-ref", ref_name, head_sha, cwd=cwd)

        return {
            "status": "success",
            "checkpoint_id": checkpoint_id,
            "ref": ref_name,
            "commit_sha": head_sha[:8],
            "message": name or "Manual Checkpoint"
        }

    async def list_checkpoints(self, cwd: Optional[str] = None) -> list[dict]:
        """Lists all Git checkpoints created by Carole."""
        out = await self._run_git(
            "for-each-ref", "refs/carole/checkpoints",
            "--format=%(refname:short)|%(objectname:short)|%(authordate:iso)|%(subject)",
            cwd=cwd
        )
        if not out or "Git Error" in out:
            return []

        checkpoints = []
        for line in out.splitlines():
            parts = line.split("|", 3)
            if len(parts) >= 4:
                ref_short = parts[0]
                cp_id = ref_short.split("/")[-1]
                checkpoints.append({
                    "checkpoint_id": cp_id,
                    "commit_sha": parts[1],
                    "timestamp": parts[2],
                    "message": parts[3].replace("[CAROLE CHECKPOINT] ", "").strip()
                })
        return checkpoints

    async def rollback_checkpoint(self, checkpoint_id: str, cwd: Optional[str] = None) -> dict:
        """
        Transactional rollback: reverts working tree and index to checkpoint ref.
        """
        ref_name = f"refs/carole/checkpoints/{checkpoint_id}"
        verify = await self._run_git("rev-parse", "--verify", ref_name, cwd=cwd)
        if "Git Error" in verify:
            return {"status": "error", "message": f"Checkpoint '{checkpoint_id}' not found."}

        reset_res = await self._run_git("reset", "--hard", ref_name, cwd=cwd)
        if "Git Error" in reset_res:
            return {"status": "error", "message": reset_res}

        await self._run_git("clean", "-fd", cwd=cwd)
        return {"status": "success", "message": f"Rolled back to checkpoint {checkpoint_id}."}

    async def diff_checkpoint(self, checkpoint_id: str, cwd: Optional[str] = None) -> dict:
        """
        Returns structured diff and numstat between checkpoint ref and current state.
        """
        ref_name = f"refs/carole/checkpoints/{checkpoint_id}"
        verify = await self._run_git("rev-parse", "--verify", ref_name, cwd=cwd)
        if "Git Error" in verify:
            return {"status": "error", "message": f"Checkpoint '{checkpoint_id}' not found."}

        numstat_out = await self._run_git("diff", ref_name, "HEAD", "--numstat", cwd=cwd)
        patch_out = await self._run_git("diff", ref_name, "HEAD", cwd=cwd)

        files = []
        if numstat_out and "Git Error" not in numstat_out:
            for line in numstat_out.splitlines():
                parts = line.split("\t")
                if len(parts) >= 3:
                    additions = int(parts[0]) if parts[0].isdigit() else 0
                    deletions = int(parts[1]) if parts[1].isdigit() else 0
                    files.append({
                        "file": parts[2],
                        "additions": additions,
                        "deletions": deletions
                    })

        return {
            "status": "success",
            "checkpoint_id": checkpoint_id,
            "files": files,
            "unified_diff": patch_out if "Git Error" not in patch_out else ""
        }


# Singleton
git_tools = GitTools()
