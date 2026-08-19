"""
# backend/core/tools/file_tools.py

Filesystem tools with sandbox enforcement, diff generation, and search capabilities.
"""

import os
import re
from core.config import CAROLE_HOME_DIR
import difflib
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict
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
            # Check cache first — avoids a DB round-trip on every file tool call.
            cached = self._project_workspace_cache.get(project_id)
            if cached:
                return cached

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
                    root = (workspaces_dir / slug).resolve()
                    self._project_workspace_cache[project_id] = root
                    return root

            # Fallback if project not found
            fallback = (workspaces_dir / project_id).resolve()
            self._project_workspace_cache[project_id] = fallback
            return fallback

        # No project scope: fall back to the configured workspace root.
        return self.workspace_root

    # In-process cache: project_id -> project workspace root. Avoids a DB round
    # trip on every file operation for the same project.
    _project_workspace_cache: dict = {}

    # In-process cache: team_id -> project workspace root. Avoids a DB round
    # trip on every shell/git invocation for the same team.
    _team_workspace_cache: dict = {}

    async def get_workspace_root_for_team(self, team_id: Optional[str]) -> Path:
        """Resolve a team_id to its project workspace root.

        Looks up Team -> project_id -> get_workspace_root(project_id). Used to
        scope shell and git tools to the agent's own project workspace instead
        of the shared backend root. Falls back to the default workspace root
        when team_id is missing or not a valid UUID so callers never crash.
        """
        if not team_id:
            return await self.get_workspace_root(None)

        cached = self._team_workspace_cache.get(team_id)
        if cached:
            return cached

        project_id: Optional[str] = None
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
        except Exception:
            pass

        root = await self.get_workspace_root(project_id)
        self._team_workspace_cache[team_id] = root
        return root

    async def get_team_carole_dir(self, team_id: str) -> Path:
        """Resolve a team_id to its hidden .carole directory.
        
        Returns workspaces_dir / project_slug / .carole / team_slug
        """
        project_slug = team_id
        team_slug = team_id

        try:
            import uuid as _uuid
            from core.memory.database import async_session
            from core.memory.models import Team, Project
            from sqlalchemy import select
            team_uuid = _uuid.UUID(team_id)
            async with async_session() as db:
                team = (await db.execute(select(Team).where(Team.id == team_uuid))).scalar_one_or_none()
                if team:
                    team_slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', team.name).strip('-') or str(team.id)[:8]
                    project = (await db.execute(select(Project).where(Project.id == team.project_id))).scalar_one_or_none()
                    if project:
                        project_slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', project.name).strip('-') or str(project.id)[:8]
                    else:
                        project_slug = str(team.project_id)
        except Exception:
            pass

        workspaces_dir = CAROLE_HOME_DIR / "workspaces"
        carole_dir = workspaces_dir / project_slug / ".carole" / team_slug
        carole_dir.mkdir(parents=True, exist_ok=True)
        return carole_dir

    async def _resolve_safe_path(self, relative_path: str, project_id: Optional[str] = None, allow_out_of_bounds: bool = False) -> Path:
        root = (await self.get_workspace_root(project_id)).resolve()
        joined_path = Path(root / relative_path)
        resolved_path = joined_path.resolve()

        is_inside = False
        try:
            resolved_path.relative_to(root)
            is_inside = True
        except ValueError:
            if os.name == 'nt':
                try:
                    Path(str(resolved_path).lower()).relative_to(Path(str(root).lower()))
                    is_inside = True
                except ValueError:
                    is_inside = False

        if not allow_out_of_bounds and not is_inside:
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
            safe_path = await self._resolve_safe_path(relative_path, project_id, allow_out_of_bounds=True)
            lock = self._get_lock(safe_path)
            def _sync_read():
                if not safe_path.is_file():
                    return f"Error: '{relative_path}' is not a file or does not exist."
                
                ext = safe_path.suffix.lower()
                if ext == ".docx":
                    try:
                        from markitdown import MarkItDown
                        md = MarkItDown()
                        result = md.convert(str(safe_path))
                        return result.text_content
                    except Exception as e:
                        try:
                            # fallback
                            import docx
                            doc = docx.Document(safe_path)
                            return "\n".join([paragraph.text for paragraph in doc.paragraphs])
                        except Exception as inner_e:
                            return f"Error reading docx file: {str(e)} - fallback also failed: {str(inner_e)}"
                elif ext == ".pdf":
                    try:
                        import PyPDF2
                        with open(safe_path, "rb") as f:
                            reader = PyPDF2.PdfReader(f)
                            text = ""
                            for page in reader.pages:
                                text += page.extract_text() + "\n"
                            return text
                    except Exception as e:
                        return f"Error reading pdf file: {str(e)}"
                
                try:
                    with open(safe_path, "r", encoding="utf-8") as f:
                        return f.read()
                except UnicodeDecodeError:
                    return "[Binary file: cannot display as text]"
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
                await code_graph.mark_file_active(relative_path, agent_name, project_id)
                try:
                    return await asyncio.to_thread(_sync_write)
                finally:
                    await code_graph.clear_file_active(relative_path, project_id)
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
                await code_graph.mark_file_active(relative_path, agent_name, project_id)
                try:
                    return await asyncio.to_thread(_sync_edit)
                finally:
                    await code_graph.clear_file_active(relative_path, project_id)
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
                await code_graph.mark_file_active(relative_path, agent_name, project_id)
                try:
                    return await asyncio.to_thread(_sync_append)
                finally:
                    await code_graph.clear_file_active(relative_path, project_id)
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
                await code_graph.mark_file_active(relative_path, agent_name, project_id)
                try:
                    return await asyncio.to_thread(_sync_delete)
                finally:
                    await code_graph.clear_file_active(relative_path, project_id)
        except Exception as e:
            return f"Error deleting file: {str(e)}"

    async def list_directory(self, relative_path: str = ".", project_id: Optional[str] = None) -> str:
        try:
            safe_path = await self._resolve_safe_path(relative_path, project_id, allow_out_of_bounds=True)
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

    async def diff_files(
        self,
        path_a: str,
        path_b: str,
        team_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> str:
        """
        Compare two files in the workspace and return a unified diff.
        Useful for reviewing changes between versions of the same file, or comparing
        two different files side-by-side.

        Args:
            path_a: Relative path to the first (original) file.
            path_b: Relative path to the second (new) file.
        """
        workspace = await self.get_workspace_root(project_id)

        def _sync_diff():
            abs_a = (workspace / path_a).resolve()
            abs_b = (workspace / path_b).resolve()

            # Sandbox check — use relative_to() for case-safe enforcement on Windows
            try:
                abs_a.relative_to(workspace)
            except ValueError:
                return f"Error: path_a '{path_a}' is outside the workspace."
            try:
                abs_b.relative_to(workspace)
            except ValueError:
                return f"Error: path_b '{path_b}' is outside the workspace."
            if not abs_a.exists():
                return f"Error: File not found: {path_a}"
            if not abs_b.exists():
                return f"Error: File not found: {path_b}"

            try:
                lines_a = abs_a.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                lines_b = abs_b.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            except Exception as e:
                return f"Error reading files: {str(e)}"

            diff_lines = list(difflib.unified_diff(
                lines_a, lines_b,
                fromfile=path_a,
                tofile=path_b,
                lineterm="",
            ))

            if not diff_lines:
                return f"No differences found between '{path_a}' and '{path_b}'."

            added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
            removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
            summary = f"Diff: {path_a} → {path_b} | +{added} lines, -{removed} lines\n\n"
            return summary + "\n".join(diff_lines)

        return await asyncio.to_thread(_sync_diff)


# Singleton file tools instance
file_tools = FileTools()

