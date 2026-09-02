"""
# backend/core/tools/code_analysis_tools.py

Code analysis tools for agents to understand codebases.

- find_function: Locate function/class definitions by name.
- find_todos: Find TODO/FIXME/HACK comments across files.
- count_lines: Count lines of code, comments, and blanks.
- analyze_imports: List all imports in a Python/JS/TS file.
- check_syntax: Validate Python syntax without executing.
"""

import os
import re
import ast
from pathlib import Path
from typing import Optional, List, Dict, Any


class CodeAnalysisTools:
    def __init__(self, workspace_root: str = None):
        if not workspace_root:
            workspace_root = os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[3]))
        self.workspace_root = Path(workspace_root).resolve()

    def _resolve_safe_path(self, relative_path: str) -> Path:
        joined = Path(self.workspace_root / relative_path)
        resolved = joined.resolve()
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError:
            raise PermissionError("Access Denied: Path outside sandbox.")
        return resolved

    _SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.next', 'venv', '.venv', 'dist', 'build'}

    def find_function(self, name: str, relative_path: str = ".") -> str:
        """Finds function/class definitions matching a name across files."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            pattern = re.compile(
                rf"^\s*(?:def|class|function|const|let|var|export\s+(?:default\s+)?(?:function|class|const))\s+{re.escape(name)}\b",
                re.MULTILINE
            )
            results = []
            target = safe_path if safe_path.is_file() else None

            def scan(fpath: Path):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if pattern.search(line):
                                rel = fpath.relative_to(self.workspace_root)
                                results.append(f"{rel}:{i}: {line.rstrip()}")
                except (UnicodeDecodeError, PermissionError):
                    pass

            if target:
                scan(target)
            else:
                for root, dirs, files in os.walk(safe_path):
                    dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS and not d.startswith('.')]
                    for fname in files:
                        if fname.endswith(('.py', '.js', '.ts', '.tsx', '.jsx', '.go', '.rs', '.java')):
                            scan(Path(root) / fname)
                            if len(results) >= 30:
                                break

            if not results:
                return f"No definitions found for '{name}'."
            return f"Found {len(results)} definition(s) for '{name}':\n" + "\n".join(results)
        except Exception as e:
            return f"Error: {str(e)}"

    def find_todos(self, relative_path: str = ".") -> str:
        """Finds TODO/FIXME/HACK/XXX comments across files."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            pattern = re.compile(r"#\s*(TODO|FIXME|HACK|XXX|BUG|NOTE)\b.*|//\s*(TODO|FIXME|HACK|XXX|BUG|NOTE)\b.*", re.IGNORECASE)
            results = []

            def scan(fpath: Path):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            m = pattern.search(line)
                            if m:
                                rel = fpath.relative_to(self.workspace_root)
                                results.append(f"{rel}:{i}: {line.strip()}")
                except (UnicodeDecodeError, PermissionError):
                    pass

            if safe_path.is_file():
                scan(safe_path)
            else:
                for root, dirs, files in os.walk(safe_path):
                    dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS and not d.startswith('.')]
                    for fname in files:
                        if fname.endswith(('.py', '.js', '.ts', '.tsx', '.jsx', '.go', '.rs', '.java', '.css', '.html')):
                            scan(Path(root) / fname)
                            if len(results) >= 50:
                                break

            if not results:
                return "No TODO/FIXME/HACK comments found."
            return f"Found {len(results)} comment(s):\n" + "\n".join(results)
        except Exception as e:
            return f"Error: {str(e)}"

    def count_lines(self, relative_path: str) -> str:
        """Counts total lines, code lines, comment lines, and blank lines."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_file():
                return f"Error: '{relative_path}' is not a file."

            total = code = comments = blanks = 0
            ext = safe_path.suffix
            comment_char = "#" if ext == ".py" else "//"

            with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    total += 1
                    stripped = line.strip()
                    if not stripped:
                        blanks += 1
                    elif stripped.startswith(comment_char):
                        comments += 1
                    else:
                        code += 1

            return (
                f"📊 Line count for '{relative_path}':\n"
                f"  Total:    {total}\n"
                f"  Code:     {code}\n"
                f"  Comments: {comments}\n"
                f"  Blank:    {blanks}"
            )
        except Exception as e:
            return f"Error: {str(e)}"

    def analyze_imports(self, relative_path: str) -> str:
        """Lists all import statements in a file."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_file():
                return f"Error: '{relative_path}' is not a file."

            imports = []
            with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    stripped = line.strip()
                    if re.match(r"^(import |from .+ import |const .+ = require\(|import .+ from )", stripped):
                        imports.append(f"  L{i}: {stripped}")

            if not imports:
                return f"No imports found in '{relative_path}'."
            return f"📦 Imports in '{relative_path}' ({len(imports)}):\n" + "\n".join(imports)
        except Exception as e:
            return f"Error: {str(e)}"

    def check_syntax(self, relative_path: str) -> str:
        """Validates Python syntax without executing the file."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_file():
                return f"Error: '{relative_path}' is not a file."
            if not safe_path.suffix == ".py":
                return "Error: check_syntax only supports .py files."

            with open(safe_path, "r", encoding="utf-8") as f:
                source = f.read()

            ast.parse(source, filename=relative_path)
            return f"✅ Syntax OK: '{relative_path}' has no Python syntax errors."
        except SyntaxError as e:
            return f"❌ Syntax Error in '{relative_path}':\n  Line {e.lineno}: {e.msg}\n  {e.text.strip() if e.text else ''}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def analyze_impact(self, file_path: str, project_id: Optional[str] = None) -> str:
        """Analyzes the impact of modifying a file using the Code Knowledge Graph."""
        from core.knowledge.code_graph import code_graph
        try:
            safe_path = self._resolve_safe_path(file_path)
            try:
                path_str = str(safe_path.relative_to(self.workspace_root)).replace("\\", "/")
            except ValueError:
                return f"Error: '{file_path}' is not within the workspace."

            graph = await code_graph.get_graph(project_id)
            if not graph.has_node(path_str):
                return f"No dependency graph data for '{path_str}'."

            # Find all files that depend on this file
            dependent_files = list(graph.predecessors(path_str))
            
            output = [f"🔍 Impact Analysis for '{path_str}':"]
            if dependent_files:
                output.append(f"  {len(dependent_files)} file(s) depend on this:")
                for dep in dependent_files:
                    output.append(f"    - {dep}")
            else:
                output.append("  No internal files depend on this.")

            # Check active editors
            pid = "default"
            warnings = []
            if pid in code_graph.active_editors:
                active_target = code_graph.active_editors[pid].get(path_str)
                if active_target:
                    warnings.append(f"⚠️ TARGET FILE actively edited by: {', '.join(active_target)}")
                
                for dep in dependent_files:
                    active_dep = code_graph.active_editors[pid].get(dep)
                    if active_dep:
                        warnings.append(f"⚠️ DEPENDENT FILE '{dep}' actively edited by: {', '.join(active_dep)}")
                    
            if warnings:
                output.append("\n" + "\n".join(warnings))
            else:
                output.append("\n✅ No active editing conflicts detected.")

            return "\n".join(output)
        except Exception as e:
            return f"Error analyzing impact: {str(e)}"

    async def get_symbol_callers(self, symbol_name: str, project_id: Optional[str] = None) -> str:
        """Finds all files and lines that import or invoke a symbol across the workspace."""
        from core.knowledge.code_graph import code_graph
        try:
            callers = await code_graph.get_symbol_callers(symbol_name, project_id)
            if not callers:
                return f"No callers or imports found for symbol '{symbol_name}'."
            
            lines = [f"Found {len(callers)} reference(s) to symbol '{symbol_name}':"]
            for c in callers:
                lines.append(f"  • {c['file']}:{c['line']} -> {c['code']}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error locating symbol callers: {str(e)}"

    async def get_symbol_callees(self, function_name: str, file_path: str, project_id: Optional[str] = None) -> str:
        """Finds all function calls invoked within a specific function/class definition."""
        from core.knowledge.code_graph import code_graph
        try:
            safe_path = self._resolve_safe_path(file_path)
            rel_path = str(safe_path.relative_to(self.workspace_root)).replace("\\", "/")
            callees = await code_graph.get_symbol_callees(function_name, rel_path, project_id)
            if not callees:
                return f"No internal function calls found inside '{function_name}' in '{file_path}'."
            return f"Function '{function_name}' calls {len(callees)} function(s):\n  " + ", ".join(callees)
        except Exception as e:
            return f"Error analyzing symbol callees: {str(e)}"


# Singleton
code_analysis_tools = CodeAnalysisTools()
