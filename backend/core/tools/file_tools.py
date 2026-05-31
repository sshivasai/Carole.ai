"""
# backend/core/tools/file_tools.py

Filesystem tools with sandbox enforcement, diff generation, and search capabilities.
"""

import os
import re
import difflib
import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List


@dataclass
class FileChangeResult:
    """Return type for write/edit operations — carries the diff alongside the result."""
    message: str
    path: str = ""
    action: str = ""
    before_content: str = ""
    after_content: str = ""
    diff: str = ""


class FileTools:
    def __init__(self, workspace_root: str = None):
        if not workspace_root:
            workspace_root = os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[3]))
        self.workspace_root = Path(workspace_root).resolve()

    def _resolve_safe_path(self, relative_path: str) -> Path:
        joined_path = Path(self.workspace_root / relative_path)
        resolved_path = joined_path.resolve()
        if not str(resolved_path).startswith(str(self.workspace_root)):
            raise PermissionError(
                f"Access Denied: Path traversal to '{resolved_path}' outside sandbox '{self.workspace_root}'."
            )
        return resolved_path

    @staticmethod
    def _generate_diff(path: str, before: str, after: str) -> str:
        before_lines = before.splitlines(keepends=True)
        after_lines = after.splitlines(keepends=True)
        diff = difflib.unified_diff(before_lines, after_lines, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="")
        return "\n".join(diff)

    def read_file(self, relative_path: str) -> str:
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_file():
                return f"Error: '{relative_path}' is not a file or does not exist."
            with open(safe_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def write_file(self, relative_path: str, content: str) -> FileChangeResult:
        try:
            safe_path = self._resolve_safe_path(relative_path)
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
                message=f"Success: File '{relative_path}' written ({len(content)} bytes).",
                path=relative_path, action=action, before_content=before, after_content=content, diff=diff,
            )
        except Exception as e:
            return FileChangeResult(message=f"Error writing file: {str(e)}")

    def edit_file(self, relative_path: str, target_content: str, replacement_content: str) -> FileChangeResult:
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_file():
                return FileChangeResult(message=f"Error: '{relative_path}' does not exist.")
            with open(safe_path, "r", encoding="utf-8") as f:
                before = f.read()
            if target_content not in before:
                return FileChangeResult(message="Error: Target block not found in file.")
            occurrences = before.count(target_content)
            if occurrences > 1:
                return FileChangeResult(message=f"Error: Found {occurrences} occurrences. Provide a unique block.")
            after = before.replace(target_content, replacement_content)
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(after)
            diff = self._generate_diff(relative_path, before, after)
            return FileChangeResult(
                message=f"Success: Modified '{relative_path}'.",
                path=relative_path, action="edit", before_content=before, after_content=after, diff=diff,
            )
        except Exception as e:
            return FileChangeResult(message=f"Error editing file: {str(e)}")

    def append_file(self, relative_path: str, content: str) -> FileChangeResult:
        """Appends content to the end of an existing file."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            before = ""
            if safe_path.is_file():
                with open(safe_path, "r", encoding="utf-8") as f:
                    before = f.read()
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            with open(safe_path, "a", encoding="utf-8") as f:
                f.write(content)
            after = before + content
            diff = self._generate_diff(relative_path, before, after)
            return FileChangeResult(
                message=f"Success: Appended {len(content)} bytes to '{relative_path}'.",
                path=relative_path, action="append", before_content=before, after_content=after, diff=diff,
            )
        except Exception as e:
            return FileChangeResult(message=f"Error appending to file: {str(e)}")

    def delete_file(self, relative_path: str) -> str:
        """Deletes a file inside the sandbox."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_file():
                return f"Error: '{relative_path}' does not exist."
            safe_path.unlink()
            return f"Success: Deleted '{relative_path}'."
        except Exception as e:
            return f"Error deleting file: {str(e)}"

    def list_directory(self, relative_path: str = ".") -> str:
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_dir():
                return f"Error: '{relative_path}' is not a directory."
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

    def grep_search(self, pattern: str, relative_path: str = ".", case_sensitive: bool = True) -> str:
        """Searches file contents for a regex pattern. Returns matching lines with file:line references."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            flags = 0 if case_sensitive else re.IGNORECASE
            compiled = re.compile(pattern, flags)
            results = []
            max_results = 50

            def search_file(fpath: Path):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if compiled.search(line):
                                rel = fpath.relative_to(self.workspace_root)
                                results.append(f"{rel}:{line_num}: {line.rstrip()}")
                                if len(results) >= max_results:
                                    return
                except (UnicodeDecodeError, PermissionError):
                    pass

            if safe_path.is_file():
                search_file(safe_path)
            else:
                for root, dirs, files in os.walk(safe_path):
                    # Skip hidden dirs and common non-code dirs
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', '__pycache__', '.git', '.next', 'venv')]
                    for fname in sorted(files):
                        if len(results) >= max_results:
                            break
                        search_file(Path(root) / fname)

            if not results:
                return f"No matches found for pattern '{pattern}'."
            header = f"Found {len(results)} match(es) for '{pattern}':\n"
            return header + "\n".join(results)
        except re.error as e:
            return f"Error: Invalid regex pattern: {str(e)}"
        except Exception as e:
            return f"Error during grep search: {str(e)}"

    def glob_search(self, pattern: str, relative_path: str = ".") -> str:
        """Finds files matching a glob pattern (e.g. '**/*.py')."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_dir():
                return f"Error: '{relative_path}' is not a directory."
            matches = []
            for match in sorted(safe_path.glob(pattern)):
                # Skip hidden and common noise directories
                parts = match.relative_to(self.workspace_root).parts
                if any(p.startswith('.') or p in ('node_modules', '__pycache__', '.next', 'venv') for p in parts):
                    continue
                rel = match.relative_to(self.workspace_root)
                if match.is_file():
                    matches.append(f"[FILE] {rel} ({match.stat().st_size} bytes)")
                else:
                    matches.append(f"[DIR]  {rel}/")
                if len(matches) >= 100:
                    break
            if not matches:
                return f"No files found matching pattern '{pattern}'."
            return f"Found {len(matches)} match(es) for '{pattern}':\n" + "\n".join(matches)
        except Exception as e:
            return f"Error during glob search: {str(e)}"


    def copy_file(self, source: str, destination: str) -> str:
        """Copies a file within the sandbox."""
        import shutil
        try:
            src = self._resolve_safe_path(source)
            dst = self._resolve_safe_path(destination)
            if not src.is_file():
                return f"Error: Source '{source}' does not exist."
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            return f"Success: Copied '{source}' → '{destination}'."
        except Exception as e:
            return f"Error copying file: {str(e)}"

    def move_file(self, source: str, destination: str) -> str:
        """Moves/renames a file within the sandbox."""
        import shutil
        try:
            src = self._resolve_safe_path(source)
            dst = self._resolve_safe_path(destination)
            if not src.exists():
                return f"Error: Source '{source}' does not exist."
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return f"Success: Moved '{source}' → '{destination}'."
        except Exception as e:
            return f"Error moving file: {str(e)}"

    def create_directory(self, relative_path: str) -> str:
        """Creates a directory (and parents) within the sandbox."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            safe_path.mkdir(parents=True, exist_ok=True)
            return f"Success: Directory '{relative_path}' created."
        except Exception as e:
            return f"Error creating directory: {str(e)}"


# Singleton file tools instance
file_tools = FileTools()
