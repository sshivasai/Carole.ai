"""
# backend/core/tools/file_tools.py

Filesystem tools with sandbox enforcement, diff generation, and search capabilities.
"""

import os
import re
from core.config import CAROLE_HOME_DIR
from core.tools.context import file_read_scope
import difflib
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
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


def _normalize_quotes(text: str) -> str:
    """Normalize unicode smart/curly quotes to standard ASCII quotes."""
    if not text:
        return text
    # Double quotes: “ ” „ ” « »
    text = re.sub(r'[\u201c\u201d\u201e\u00ab\u00bb]', '"', text)
    # Single quotes: ‘ ’ ‚ ’ ` ´
    text = re.sub(r'[\u2018\u2019\u201a\u0060\u00b4]', "'", text)
    return text


def _validate_code_syntax(path_str: str, content: str) -> Optional[str]:
    """Validates code syntax before writing or editing files on disk.

    Inspired by SWE-agent's Agent-Computer Interface (ACI) proactive error mitigation:
    catches syntax errors at the tool boundary before they touch disk or break test suites.
    Returns an error message string if invalid, or None if valid/unsupported.
    """
    if not content or not content.strip():
        return None

    ext = Path(path_str).suffix.lower()

    # 1. Python Syntax Validation via native ast.parse
    if ext == ".py":
        try:
            import ast
            ast.parse(content, filename=path_str)
        except SyntaxError as e:
            line_snippet = ""
            if e.text:
                line_snippet = f"\n  Line {e.lineno}: {e.text.rstrip()}"
                if e.offset:
                    line_snippet += f"\n          {' ' * (e.offset - 1)}^"
            return (
                f"✗ Syntax Error: Your edit introduced invalid Python syntax on line {e.lineno}: {e.msg}{line_snippet}\n"
                f"File '{path_str}' was NOT written to disk. Please correct the syntax error and retry."
            )
        except Exception:
            pass

    # 2. JSON Syntax Validation
    elif ext == ".json":
        try:
            import json
            json.loads(content)
        except json.JSONDecodeError as e:
            return (
                f"✗ JSON Syntax Error in '{path_str}' at line {e.lineno}, column {e.colno}: {e.msg}\n"
                f"File was NOT written to disk. Please fix the JSON formatting and retry."
            )

    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        # A delimiter balancer cannot distinguish regex literals, templates, or
        # JSX. Use the language grammar already used by code indexing.
        from core.knowledge.ast_parser import syntax_has_error
        language = {".js": "javascript", ".jsx": "javascript",
                    ".ts": "typescript", ".tsx": "tsx"}[ext]
        if syntax_has_error(content, language):
            return f"✗ Syntax Error in '{path_str}'. File was NOT written to disk. Correct the syntax and retry."

    return None


class FileTools:
    def __init__(self, workspace_root: str = None):
        if not workspace_root:
            workspace_root = os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[3]))
        self.workspace_root = Path(workspace_root).resolve()
        self._locks: Dict[str, asyncio.Lock] = {}
        # Session / team read tracking: maps scope_id (team_id or 'global') -> {normalized_abs_path: mtime}
        # Used for Pre-Read enforcement and FILE_UNCHANGED_STUB compression
        self._read_state: Dict[str, Dict[str, float]] = {}

    async def get_workspace_root(self, project_id: Optional[str] = None, db: Optional[AsyncSession] = None) -> Path:
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
                project_uuid = uuid.UUID(str(project_id))
            except ValueError:
                safe_id = re.sub(r'[^a-zA-Z0-9_-]+', '', str(project_id))
                return (workspaces_dir / safe_id).resolve()

            project = None
            if db is not None:
                try:
                    result = await db.execute(select(Project).where(Project.id == project_uuid))
                    project = result.scalar_one_or_none()
                except Exception:
                    pass
            else:
                try:
                    async with async_session() as session:
                        result = await session.execute(select(Project).where(Project.id == project_uuid))
                        project = result.scalar_one_or_none()
                except Exception:
                    pass

            if project:
                custom_path = getattr(project, "custom_workspace_path", None)
                if custom_path and str(custom_path).strip():
                    root = Path(str(custom_path).strip()).resolve()
                    root.mkdir(parents=True, exist_ok=True)
                    self._project_workspace_cache[project_id] = root
                    return root

                slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', project.name).strip('-')
                if not slug:
                    slug = str(project.id)[:8]
                root = (workspaces_dir / slug).resolve()
                self._project_workspace_cache[project_id] = root
                return root

            # Fallback if project not found
            safe_id = re.sub(r'[^a-zA-Z0-9_-]+', '', str(project_id))
            fallback = (workspaces_dir / safe_id).resolve()
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

    async def get_team_carole_dir(self, team_id: str, db: Optional[AsyncSession] = None) -> Path:
        """Resolve stable internal storage by project/team IDs; names may collide."""
        import uuid
        from core.memory.models import Team, Project
        from core.memory.database import async_session
        from sqlalchemy import select
        team_uuid = uuid.UUID(str(team_id))
        async def resolve(session):
            team = await session.get(Team, team_uuid)
            if team is None:
                raise ValueError("Team not found")
            project = await session.get(Project, team.project_id)
            if project is None:
                raise ValueError("Project not found")
            base = (CAROLE_HOME_DIR / "workspaces").resolve()
            target = (base / str(project.id) / ".carole" / str(team.id)).resolve()
            if not target.is_relative_to(base):
                raise ValueError("Internal team directory escapes application storage")
            if not target.exists():
                slug = lambda name: re.sub(r'[^a-zA-Z0-9_-]+', '-', name).strip('-')
                project_slug, team_slug = slug(project.name), slug(team.name)
                legacy = (base / project_slug / ".carole" / team_slug).resolve()
                # Copy legacy data only when its old name-based ownership is
                # unambiguous. Keep the original directory as a recovery copy.
                if project_slug and team_slug and legacy.is_relative_to(base) and legacy.is_dir():
                    projects = (await session.scalars(select(Project))).all()
                    teams = (await session.scalars(select(Team).where(Team.project_id == project.id))).all()
                    if sum(slug(row.name) == project_slug for row in projects) == 1 and sum(slug(row.name) == team_slug for row in teams) == 1:
                        import shutil
                        await asyncio.to_thread(shutil.copytree, legacy, target, symlinks=True, dirs_exist_ok=True)
            target.mkdir(parents=True, exist_ok=True)
            return target
        if db is not None:
            return await resolve(db)
        async with async_session() as session:
            return await resolve(session)

    async def _resolve_safe_path(self, relative_path: str, project_id: Optional[str] = None, allow_out_of_bounds: bool = False, db: Optional[AsyncSession] = None) -> Path:
        if not relative_path or not str(relative_path).strip():
            raise ValueError("Path cannot be empty or whitespace.")
        root = (await self.get_workspace_root(project_id, db=db)).resolve()
        raw = Path(relative_path)
        if raw.is_absolute():
            resolved_path = raw.resolve()
        else:
            resolved_path = (root / relative_path).resolve()

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

        if allow_out_of_bounds and not is_inside and project_id:
            from core.auth.instance_owner import assert_project_instance_owner
            try:
                await assert_project_instance_owner(project_id)
            except Exception as exc:
                raise PermissionError("External host files require the configured instance owner") from exc
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

    FILE_UNCHANGED_STUB = (
        "File unchanged since last read. The content from the earlier read_file tool_result in this conversation is still current — refer to that instead of re-reading."
    )

    async def read_file(
        self,
        relative_path: str,
        project_id: Optional[str] = None,
        team_id: Optional[str] = None,
        force: bool = False,
        start_line: int = 1,
        end_line: Optional[int] = None,
    ) -> str:
        try:
            allow_out_of_bounds = Path(relative_path).is_absolute() if relative_path and str(relative_path).strip() else False
            safe_path = await self._resolve_safe_path(relative_path, project_id, allow_out_of_bounds=allow_out_of_bounds)
            lock = self._get_lock(safe_path)
            scope = file_read_scope.get() or team_id or "global"
            norm_path = str(safe_path.resolve())

            def _sync_read():
                if not safe_path.is_file():
                    return f"Error: '{relative_path}' is not a file or does not exist."
                
                mtime = safe_path.stat().st_mtime
                if not force and scope in self._read_state and norm_path in self._read_state[scope]:
                    last_mtime = self._read_state[scope][norm_path]
                    if mtime <= last_mtime:
                        return self.FILE_UNCHANGED_STUB

                ext = safe_path.suffix.lower()
                content = None
                if ext == ".docx":
                    try:
                        from markitdown import MarkItDown
                        md = MarkItDown()
                        result = md.convert(str(safe_path))
                        content = result.text_content
                    except Exception as e:
                        try:
                            import docx
                            doc = docx.Document(safe_path)
                            content = "\n".join([paragraph.text for paragraph in doc.paragraphs])
                        except Exception as inner_e:
                            return f"Error reading docx file: {str(e)} - fallback also failed: {str(inner_e)}"
                elif ext == ".pdf":
                    try:
                        import PyPDF2
                        with open(safe_path, "rb") as f:
                            reader = PyPDF2.PdfReader(f)
                            text = ""
                            for page in reader.pages:
                                text += (page.extract_text() or "") + "\n"
                            content = text
                    except Exception as e:
                        return f"Error reading pdf file: {str(e)}"
                
                if content is None:
                    try:
                        with open(safe_path, "r", encoding="utf-8") as f:
                            content = f.read()
                    except UnicodeDecodeError:
                        return "[Binary file: cannot display as text]"
                
                # Record successful read state
                self._read_state.setdefault(scope, {})[norm_path] = mtime
                if start_line != 1 or end_line is not None:
                    if start_line < 1 or (end_line is not None and end_line < start_line):
                        return "Error: Invalid line range. Lines are numbered from 1."
                    return "".join(content.splitlines(keepends=True)[start_line - 1:end_line])
                return content

            async with lock:
                return await asyncio.to_thread(_sync_read)
        except Exception as e:
            return f"Error reading file: {str(e)}"

    async def write_file(
        self,
        relative_path: str,
        content: str,
        agent_name: str = "Unknown",
        project_id: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> FileChangeResult:
        try:
            safe_path = await self._resolve_safe_path(relative_path, project_id)
            lock = self._get_lock(safe_path)
            scope = file_read_scope.get() or team_id or "global"
            norm_path = str(safe_path.resolve())

            if self.FILE_UNCHANGED_STUB in content or "status=\"unchanged\"" in content:
                return FileChangeResult(
                    message="Error: You are attempting to write the 'unchanged' tool stub or metadata back to the file. "
                            "If you want to modify this file, you must write the actual code content, not the unchanged reference message."
                )

            # Proactive AST Syntax Gate (SWE-agent ACI pattern)
            syntax_err = await asyncio.to_thread(_validate_code_syntax, relative_path, content)
            if syntax_err:
                return FileChangeResult(message=syntax_err)

            def _sync_write():
                if safe_path.is_dir():
                    return FileChangeResult(message=f"Error: Target path '{relative_path}' is a directory, not a file.")
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
                # Invalidate cached read state so subsequent reads fetch the fresh content
                for s in self._read_state.values():
                    s.pop(norm_path, None)
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

    async def edit_file(
        self,
        relative_path: str,
        target_content: str,
        replacement_content: str,
        agent_name: str = "Unknown",
        project_id: Optional[str] = None,
        team_id: Optional[str] = None,
        enforce_pre_read: bool = True
    ) -> FileChangeResult:
        try:
            safe_path = await self._resolve_safe_path(relative_path, project_id)
            lock = self._get_lock(safe_path)
            scope = file_read_scope.get() or team_id or "global"
            norm_path = str(safe_path.resolve())

            if self.FILE_UNCHANGED_STUB in replacement_content or "status=\"unchanged\"" in replacement_content:
                return FileChangeResult(
                    message="Error: You are attempting to write the 'unchanged' tool stub or metadata back to the file. "
                            "If you want to modify this file, you must write the actual code content, not the unchanged reference message."
                )

            def _sync_edit():
                if not safe_path.is_file():
                    return FileChangeResult(message=f"Error: '{relative_path}' does not exist.")
                
                # Strict Pre-Read Enforcement
                if enforce_pre_read:
                    team_reads = self._read_state.get(scope, {})
                    if norm_path not in team_reads:
                        return FileChangeResult(
                            message=f"Error: File '{relative_path}' has not been read yet in this conversation session. "
                                    f"You must use read_file at least once before attempting to edit it."
                        )
                    last_read_mtime = team_reads[norm_path]
                    current_mtime = safe_path.stat().st_mtime
                    if current_mtime > last_read_mtime:
                        return FileChangeResult(
                            message=f"Error: File '{relative_path}' has been modified on disk since it was last read. "
                                    f"Please call read_file again to see the updated contents before editing."
                        )

                with open(safe_path, "r", encoding="utf-8") as f:
                    before = f.read()
                target = target_content
                if target not in before:
                    # Fallback 1: Line-ending normalization (\r\n vs \n)
                    if "\r\n" in before and "\r\n" not in target:
                        crlf_target = target.replace("\n", "\r\n")
                        if crlf_target in before:
                            target = crlf_target
                    elif "\r\n" in target and "\r\n" not in before:
                        lf_target = target.replace("\r\n", "\n")
                        if lf_target in before:
                            target = lf_target

                if target not in before:
                    # Fallback 2: quote-normalized matching (handles LLM unicode curly quotes)
                    norm_before = _normalize_quotes(before)
                    norm_target = _normalize_quotes(target)
                    if norm_target in norm_before:
                        idx = norm_before.find(norm_target)
                        target = before[idx:idx + len(target)]
                    else:
                        return FileChangeResult(
                            message="Error: Target block not found in file. Ensure exact character-for-character match including indentation."
                        )
                occurrences = before.count(target)
                if occurrences > 1:
                    return FileChangeResult(
                        message=f"Error: Found {occurrences} occurrences of target block in '{relative_path}'. "
                                f"Provide a larger block with 2-4 surrounding lines to uniquely identify the instance."
                    )
                # Match newline convention of target in replacement
                rep = replacement_content
                if "\r\n" in target and "\r\n" not in rep:
                    rep = rep.replace("\n", "\r\n")
                elif "\r\n" not in target and "\r\n" in rep:
                    rep = rep.replace("\r\n", "\n")
                after = before.replace(target, rep, 1)

                # Proactive AST Syntax Gate (SWE-agent ACI pattern)
                syntax_err = _validate_code_syntax(relative_path, after)
                if syntax_err:
                    return FileChangeResult(message=syntax_err)

                with open(safe_path, "w", encoding="utf-8") as f:
                    f.write(after)
                diff = self._generate_diff(relative_path, before, after)
                # Update read state to current mtime
                self._read_state.setdefault(scope, {})[norm_path] = safe_path.stat().st_mtime
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

    async def append_file(
        self,
        relative_path: str,
        content: str,
        agent_name: str = "Unknown",
        project_id: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> FileChangeResult:
        """Appends content to the end of an existing file."""
        try:
            safe_path = await self._resolve_safe_path(relative_path, project_id)
            lock = self._get_lock(safe_path)
            scope = file_read_scope.get() or team_id or "global"
            norm_path = str(safe_path.resolve())

            if self.FILE_UNCHANGED_STUB in content or "status=\"unchanged\"" in content:
                return FileChangeResult(
                    message="Error: You are attempting to write the 'unchanged' tool stub or metadata back to the file. "
                            "If you want to modify this file, you must write the actual code content, not the unchanged reference message."
                )

            def _sync_append():
                if safe_path.is_dir():
                    return FileChangeResult(message=f"Error: Target path '{relative_path}' is a directory, not a file.")
                before = ""
                if safe_path.is_file():
                    with open(safe_path, "r", encoding="utf-8") as f:
                        before = f.read()
                after = before + content

                # Proactive AST Syntax Gate (SWE-agent ACI pattern)
                syntax_err = _validate_code_syntax(relative_path, after)
                if syntax_err:
                    return FileChangeResult(message=syntax_err)

                safe_path.parent.mkdir(parents=True, exist_ok=True)
                with open(safe_path, "a", encoding="utf-8") as f:
                    f.write(content)
                diff = self._generate_diff(relative_path, before, after)
                self._read_state.setdefault(scope, {})[norm_path] = safe_path.stat().st_mtime
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
            return FileChangeResult(message=f"Error appending file: {str(e)}")

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
            allow_out_of_bounds = Path(relative_path).is_absolute() if relative_path and str(relative_path).strip() else False
            safe_path = await self._resolve_safe_path(relative_path, project_id, allow_out_of_bounds=allow_out_of_bounds)
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
            is_abs = Path(relative_path).is_absolute() if relative_path and str(relative_path).strip() else False
            safe_path = await self._resolve_safe_path(relative_path, project_id, allow_out_of_bounds=is_abs)
            root_path = (safe_path if safe_path.is_dir() else safe_path.parent) if is_abs else await self.get_workspace_root(project_id)
            def _sync_grep():
                flags = 0 if case_sensitive else re.IGNORECASE
                compiled = re.compile(pattern, flags)
                results = []
                max_results = 50
                scanned_files = 0
                max_scanned_files = 5000

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
                            scanned_files += 1
                            if scanned_files > max_scanned_files or len(results) >= max_results:
                                break
                            search_file(Path(root) / fname)
                        if scanned_files > max_scanned_files or len(results) >= max_results:
                            break

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
            is_abs = Path(relative_path).is_absolute() if relative_path and str(relative_path).strip() else False
            safe_path = await self._resolve_safe_path(relative_path, project_id, allow_out_of_bounds=is_abs)
            root_path = (safe_path if safe_path.is_dir() else safe_path.parent) if is_abs else await self.get_workspace_root(project_id)
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
        """Copies a file or directory into or within the workspace.
        Source can be an absolute external path or a workspace-relative path.
        Destination must resolve within the workspace sandbox.
        """
        import shutil
        try:
            src_is_abs = Path(source).is_absolute() if source and str(source).strip() else False
            src = await self._resolve_safe_path(source, project_id, allow_out_of_bounds=src_is_abs)
            dst = await self._resolve_safe_path(destination, project_id, allow_out_of_bounds=False)
            
            def _sync_copy():
                if not src.exists():
                    return f"Error: Source '{source}' does not exist."
                if src.is_dir():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
                    return f"Success: Copied directory '{source}' → '{destination}'."
                elif src.is_file():
                    target_dst = dst / src.name if dst.is_dir() else dst
                    target_dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(target_dst))
                    return f"Success: Copied '{source}' → '{destination}'."
                else:
                    return f"Error: Source '{source}' is neither a file nor a directory."
                
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
        try:
            abs_a = await self._resolve_safe_path(path_a, project_id)
        except Exception as e:
            return f"Error: path_a '{path_a}' is outside the workspace: {e}"
        try:
            abs_b = await self._resolve_safe_path(path_b, project_id)
        except Exception as e:
            return f"Error: path_b '{path_b}' is outside the workspace: {e}"

        def _sync_diff():
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

