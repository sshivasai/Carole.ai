"""
# backend/core/tools/file_tools.py

This module contains tools for safely interacting with the local filesystem.

Responsibilities:
1. Provide `FileReadTool`, `FileWriteTool`, and `FileEditTool` for precise code modifications.
2. Provide `GlobTool` and `GrepTool` for searching directories and file contents.
3. Restrict agents from navigating outside of the designated workspace directory (sandbox enforcement).
4. Generate unified diffs on writes/edits for live diff streaming to the UI.
"""

import os
import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FileChangeResult:
    """Return type for write/edit operations — carries the diff alongside the result."""
    message: str
    path: str = ""
    action: str = ""  # "create", "write", "edit"
    before_content: str = ""
    after_content: str = ""
    diff: str = ""


class FileTools:
    def __init__(self, workspace_root: str = None):
        if not workspace_root:
            workspace_root = os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[3]))
        self.workspace_root = Path(workspace_root).resolve()

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """
        Enforce security sandboxing:
        - Resolves relative path to absolute form.
        - Verifies the path remains strictly inside self.workspace_root.
        - Raises PermissionError on any path traversal escape attempts (e.g. '../../').
        """
        joined_path = Path(self.workspace_root / relative_path)
        resolved_path = joined_path.resolve()
        
        if not str(resolved_path).startswith(str(self.workspace_root)):
            raise PermissionError(
                f"Access Denied: Attempted path traversal to '{resolved_path}' "
                f"which is outside of the secure sandbox boundary '{self.workspace_root}'."
            )
            
        return resolved_path

    @staticmethod
    def _generate_diff(path: str, before: str, after: str) -> str:
        """Generates a unified diff string."""
        before_lines = before.splitlines(keepends=True)
        after_lines = after.splitlines(keepends=True)
        diff = difflib.unified_diff(
            before_lines, after_lines,
            fromfile=f"a/{path}", tofile=f"b/{path}",
            lineterm=""
        )
        return "\n".join(diff)

    def read_file(self, relative_path: str) -> str:
        """Reads and returns the contents of a file inside the sandbox."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_file():
                return f"Error: '{relative_path}' is not a file or does not exist."
            with open(safe_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def write_file(self, relative_path: str, content: str) -> FileChangeResult:
        """Creates a new file or overwrites an existing one inside the sandbox.
        Returns a FileChangeResult with diff metadata."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            
            # Capture before content for diff
            before = ""
            action = "create"
            if safe_path.is_file():
                with open(safe_path, "r", encoding="utf-8") as f:
                    before = f.read()
                action = "write"

            safe_path.parent.mkdir(parents=True, exist_ok=True)
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(content)

            diff = self._generate_diff(relative_path, before, content)
            return FileChangeResult(
                message=f"Success: File '{relative_path}' successfully written ({len(content)} bytes).",
                path=relative_path,
                action=action,
                before_content=before,
                after_content=content,
                diff=diff,
            )
        except Exception as e:
            return FileChangeResult(message=f"Error writing file: {str(e)}")

    def edit_file(self, relative_path: str, target_content: str, replacement_content: str) -> FileChangeResult:
        """
        Performs a precise, safe contiguous replace in a file inside the sandbox.
        Returns a FileChangeResult with diff metadata.
        """
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_file():
                return FileChangeResult(message=f"Error: '{relative_path}' is not a file or does not exist.")
                
            with open(safe_path, "r", encoding="utf-8") as f:
                before = f.read()
                
            if target_content not in before:
                return FileChangeResult(
                    message="Error: The target block was not found in the file text. Verify exact matches and indentation."
                )
                
            occurrences = before.count(target_content)
            if occurrences > 1:
                return FileChangeResult(
                    message=f"Error: Found multiple ({occurrences}) occurrences of target block. Provide a unique block to modify."
                )
                
            after = before.replace(target_content, replacement_content)
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(after)

            diff = self._generate_diff(relative_path, before, after)
            return FileChangeResult(
                message=f"Success: Modified '{relative_path}' successfully.",
                path=relative_path,
                action="edit",
                before_content=before,
                after_content=after,
                diff=diff,
            )
        except Exception as e:
            return FileChangeResult(message=f"Error editing file: {str(e)}")

    def list_directory(self, relative_path: str = ".") -> str:
        """Lists files and directories inside the sandbox path."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_dir():
                return f"Error: '{relative_path}' is not a directory or does not exist."
            
            output = []
            for item in sorted(os.listdir(safe_path)):
                full_item = safe_path / item
                if full_item.is_dir():
                    output.append(f"[DIR]  {item}/")
                else:
                    output.append(f"[FILE] {item} ({full_item.stat().st_size} bytes)")
            
            return "\n".join(output) if output else "Directory is empty."
        except Exception as e:
            return f"Error listing directory: {str(e)}"

# Singleton file tools instance
file_tools = FileTools()

