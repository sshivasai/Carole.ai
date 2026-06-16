"""
# backend/core/tools/file_tools.py

Filesystem tools with sandbox enforcement, diff generation, and search capabilities.
"""

import os
import re
from core.config import CAROLE_HOME_DIR
import difflib
import fnmatch
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict
from contextlib import asynccontextmanager


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
        self._locks: Dict[str, asyncio.Lock] = {}

    async def get_workspace_root(self, project_id: Optional[str] = None) -> Path:
        workspaces_dir = CAROLE_HOME_DIR / "workspaces"
        if not workspaces_dir.exists():
            workspaces_dir.mkdir(parents=True, exist_ok=True)
            
        if project_id:
            from core.memory.database import async_session
            from core.memory.models import Project
            from sqlalchemy import select
            import uuid
            import re
            
            try:
                project_uuid = uuid.UUID(project_id)
            except ValueError:
                return workspaces_dir / project_id
                
            async with async_session() as db:
                result = await db.execute(select(Project).where(Project.id == project_uuid))
                project = result.scalar_one_or_none()
                if project:
                    slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', project.name).strip('-')
                    if not slug:
                        slug = str(project.id)[:8]
                    return (workspaces_dir / slug).resolve()
            
            # Fallback if project not found
            return (workspaces_dir / project_id).resolve()
            
        return workspaces_dir.resolve()

    async def _resolve_safe_path(self, relative_path: str, project_id: Optional[str] = None) -> Path:
        root = await self.get_workspace_root(project_id)
        joined_path = Path(root / relative_path)
        resolved_path = joined_path.resolve()
        if not str(resolved_path).startswith(str(root)):
            raise PermissionError(
                f"Access Denied: Path traversal to '{resolved_path}' outside sandbox '{root}'."
            )
        return resolved_path

    def _get_lock(self, path: Path) -> asyncio.Lock:
        key = str(path)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    @asynccontextmanager
    async def _acquire_locks(self, *paths: Path):
        # Deduplicate and sort by path string to prevent deadlocks
        unique_paths = sorted(list(set(str(p) for p in paths)))
        locks = []
        for p_str in unique_paths:
            if p_str not in self._locks:
                self._locks[p_str] = asyncio.Lock()
            locks.append(self._locks[p_str])
        
        for lock in locks:
            await lock.acquire()
        try:
            yield
        finally:
            for lock in reversed(locks):
                lock.release()

    @staticmethod
    def _generate_diff(path: str, before: str, after: str) -> str:
        before_lines = before.splitlines(keepends=True)
        after_lines = after.splitlines(keepends=True)
        diff = difflib.unified_diff(before_lines, after_lines, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="")
        return "\n".join(diff)

    async def read_file(self, relative_path: str, project_id: Optional[str] = None) -> str:
        try:
            safe_path = await self._resolve_safe_path(relative_path, project_id)
            lock = self._get_lock(safe_path)
            def _sync_read():
                if not safe_path.is_file():
                    return f"Error: '{relative_path}' is not a file or does not exist."
                with open(safe_path, "r", encoding="utf-8") as f:
                    return f.read()
            async with lock:
                return await asyncio.to_thread(_sync_read)
        except Exception as e:
            return f"Error reading file: {str(e)}"

    async def write_file(self, relative_path: str, content: str, agent_name: str = "Unknown", project_id: Optional[str] = None) -> FileChangeResult:
        try:
            safe_path = await self._resolve_safe_path(relative_path, project_id)
            lock = self._get_lock(safe_path)
            def _sync_write():
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
            async with lock:
                from core.knowledge.code_graph import code_graph
                code_graph.mark_file_active(relative_path, agent_name, project_id)
                try:
                    return await asyncio.to_thread(_sync_write)
                finally:
                    code_graph.clear_file_active(relative_path, project_id)
        except Exception as e:
            return FileChangeResult(message=f"Error writing file: {str(e)}")

    async def edit_file(self, relative_path: str, target_content: str, replacement_content: str, agent_name: str = "Unknown", project_id: Optional[str] = None) -> FileChangeResult:
        try:
            safe_path = await self._resolve_safe_path(relative_path, project_id)
            lock = self._get_lock(safe_path)
            def _sync_edit():
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
            async with lock:
                from core.knowledge.code_graph import code_graph
                code_graph.mark_file_active(relative_path, agent_name, project_id)
                try:
                    return await asyncio.to_thread(_sync_edit)
                finally:
                    code_graph.clear_file_active(relative_path, project_id)
        except Exception as e:
            return FileChangeResult(message=f"Error editing file: {str(e)}")

    async def append_file(self, relative_path: str, content: str, agent_name: str = "Unknown", project_id: Optional[str] = None) -> FileChangeResult:
        """Appends content to the end of an existing file."""
        try:
            safe_path = await self._resolve_safe_path(relative_path, project_id)
            lock = self._get_lock(safe_path)
            def _sync_append():
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
            async with lock:
                from core.knowledge.code_graph import code_graph
                code_graph.mark_file_active(relative_path, agent_name, project_id)
                try:
                    return await asyncio.to_thread(_sync_append)
                finally:
                    code_graph.clear_file_active(relative_path, project_id)
        except Exception as e:
            return FileChangeResult(message=f"Error appending to file: {str(e)}")

    async def delete_file(self, relative_path: str, agent_name: str = "Unknown", project_id: Optional[str] = None) -> str:
        """Deletes a file inside the sandbox."""
        try:
            safe_path = await self._resolve_safe_path(relative_path, project_id)
            lock = self._get_lock(safe_path)
            def _sync_delete():
                if not safe_path.is_file():
                    return f"Error: '{relative_path}' does not exist."
                safe_path.unlink()
                return f"Success: Deleted '{relative_path}'."
            async with lock:
                from core.knowledge.code_graph import code_graph
                code_graph.mark_file_active(relative_path, agent_name, project_id)
                try:
                    return await asyncio.to_thread(_sync_delete)
                finally:
                    code_graph.clear_file_active(relative_path, project_id)
        except Exception as e:
            return f"Error deleting file: {str(e)}"

    async def list_directory(self, relative_path: str = ".", project_id: Optional[str] = None) -> str:
        try:
            safe_path = await self._resolve_safe_path(relative_path, project_id)
            def _sync_list():
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
            return await asyncio.to_thread(_sync_list)
        except Exception as e:
            return f"Error listing directory: {str(e)}"

    async def grep_search(self, pattern: str, relative_path: str = ".", case_sensitive: bool = True, project_id: Optional[str] = None) -> str:
        """Searches file contents for a regex pattern. Returns matching lines with file:line references."""
        try:
            safe_path = await self._resolve_safe_path(relative_path, project_id)
            root_path = await self.get_workspace_root(project_id)
            def _sync_grep():
                flags = 0 if case_sensitive else re.IGNORECASE
                compiled = re.compile(pattern, flags)
                results = []
                max_results = 50

                def search_file(fpath: Path):
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            for line_num, line in enumerate(f, 1):
                                if compiled.search(line):
                                    rel = fpath.relative_to(root_path)
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
            return await asyncio.to_thread(_sync_grep)
        except re.error as e:
            return f"Error: Invalid regex pattern: {str(e)}"
        except Exception as e:
            return f"Error during grep search: {str(e)}"

    async def glob_search(self, pattern: str, relative_path: str = ".", project_id: Optional[str] = None) -> str:
        """Finds files matching a glob pattern (e.g. '**/*.py')."""
        try:
            safe_path = await self._resolve_safe_path(relative_path, project_id)
            root_path = await self.get_workspace_root(project_id)
            def _sync_glob():
                if not safe_path.is_dir():
                    return f"Error: '{relative_path}' is not a directory."
                matches = []
                for match in sorted(safe_path.glob(pattern)):
                    # Skip hidden and common noise directories
                    parts = match.relative_to(root_path).parts
                    if any(p.startswith('.') or p in ('node_modules', '__pycache__', '.next', 'venv') for p in parts):
                        continue
                    rel = match.relative_to(root_path)
                    if match.is_file():
                        matches.append(f"[FILE] {rel} ({match.stat().st_size} bytes)")
                    else:
                        matches.append(f"[DIR]  {rel}/")
                    if len(matches) >= 100:
                        break
                if not matches:
                    return f"No files found matching pattern '{pattern}'."
                return f"Found {len(matches)} match(es) for '{pattern}':\n" + "\n".join(matches)
            return await asyncio.to_thread(_sync_glob)
        except Exception as e:
            return f"Error during glob search: {str(e)}"


    async def copy_file(self, source: str, destination: str, project_id: Optional[str] = None) -> str:
        """Copies a file within the sandbox."""
        import shutil
        try:
            src = await self._resolve_safe_path(source, project_id)
            dst = await self._resolve_safe_path(destination, project_id)
            
            def _sync_copy():
                if not src.is_file():
                    return f"Error: Source '{source}' does not exist."
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))
                return f"Success: Copied '{source}' → '{destination}'."
                
            async with self._acquire_locks(src, dst):
                return await asyncio.to_thread(_sync_copy)
        except Exception as e:
            return f"Error copying file: {str(e)}"

    async def move_file(self, source: str, destination: str, project_id: Optional[str] = None) -> str:
        """Moves/renames a file within the sandbox."""
        import shutil
        try:
            src = await self._resolve_safe_path(source, project_id)
            dst = await self._resolve_safe_path(destination, project_id)
            
            def _sync_move():
                if not src.exists():
                    return f"Error: Source '{source}' does not exist."
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                return f"Success: Moved '{source}' → '{destination}'."
                
            async with self._acquire_locks(src, dst):
                return await asyncio.to_thread(_sync_move)
        except Exception as e:
            return f"Error moving file: {str(e)}"

    async def create_directory(self, relative_path: str, project_id: Optional[str] = None) -> str:
        """Creates a directory (and parents) within the sandbox."""
        try:
            safe_path = await self._resolve_safe_path(relative_path, project_id)
            def _sync_mkdir():
                safe_path.mkdir(parents=True, exist_ok=True)
                return f"Success: Directory '{relative_path}' created."
            return await asyncio.to_thread(_sync_mkdir)
        except Exception as e:
            return f"Error creating directory: {str(e)}"


# Singleton file tools instance
file_tools = FileTools()

