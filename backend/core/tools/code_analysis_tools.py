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

    def _resolve_safe_path(self, relative_path: str, workspace_root: Optional[Path] = None) -> Path:
        if not relative_path or not str(relative_path).strip():
            raise ValueError("Path cannot be empty or whitespace.")
        raw = Path(relative_path)
        if raw.is_absolute() and raw.exists():
            return raw.resolve()
        root = (workspace_root or self.workspace_root).resolve()
        joined = Path(root / relative_path)
        resolved = joined.resolve()
        is_inside = False
        try:
            resolved.relative_to(root)
            is_inside = True
        except ValueError:
            if os.name == 'nt':
                try:
                    Path(str(resolved).lower()).relative_to(Path(str(root).lower()))
                    is_inside = True
                except ValueError:
                    is_inside = False
        if not is_inside:
            raise PermissionError(f"Access Denied: Path '{resolved}' outside sandbox '{root}'.")
        return resolved

    _SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.next', 'venv', '.venv', 'dist', 'build'}

    _BINARY_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.tiff', '.svgz',
        '.mp3', '.mp4', '.wav', '.avi', '.mov', '.flac', '.ogg', '.mkv', '.webm',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt',
        '.zip', '.tar', '.gz', '.tgz', '.bz2', '.7z', '.rar', '.xz', '.zst',
        '.exe', '.dll', '.so', '.dylib', '.bin', '.iso', '.dmg',
        '.pyc', '.pyd', '.pyo', '.class', '.o', '.obj', '.a', '.lib',
        '.wasm', '.lock', '.parquet', '.db', '.sqlite', '.sqlite3'
    }

    _CODE_EXTENSIONS = {
        # Python
        '.py', '.pyi', '.pyx',
        # JavaScript / TypeScript
        '.js', '.mjs', '.cjs', '.jsx', '.ts', '.mts', '.cts', '.tsx',
        # Systems
        '.c', '.h', '.cpp', '.hpp', '.cc', '.hh', '.cxx', '.hxx', '.rs', '.go', '.zig', '.d', '.nim',
        # JVM
        '.java', '.kt', '.kts', '.scala', '.sc', '.groovy', '.clj', '.cljs',
        # Mobile / Apple
        '.swift', '.m', '.mm',
        # Scripting
        '.rb', '.php', '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd', '.lua', '.pl', '.pm', '.tcl',
        # Functional
        '.ex', '.exs', '.erl', '.hrl', '.hs', '.lhs', '.ml', '.mli', '.fs', '.fsi', '.fsx', '.lisp', '.lsp', '.rkt',
        # Web & Styling
        '.html', '.htm', '.css', '.scss', '.sass', '.less', '.vue', '.svelte',
        # Data / Query / Config
        '.sql', '.psql', '.json', '.jsonc', '.yaml', '.yml', '.toml', '.xml', '.graphql', '.gql', '.proto',
        # Documents
        '.md', '.markdown', '.rst', '.tex',
        # Build / Infra
        '.tf', '.hcl', '.dockerfile', '.mk', '.cmake'
    }

    def _is_code_file(self, fname: str) -> bool:
        """Determines if a filename is a source code or textual file for analysis."""
        lower = fname.lower()
        suffix = Path(lower).suffix
        if suffix in self._BINARY_EXTENSIONS:
            return False
        if suffix in self._CODE_EXTENSIONS:
            return True
        if lower in {
            "makefile", "gnumakefile", "dockerfile", "containerfile", "gemfile",
            "rakefile", "cmakelists.txt", "jenkinsfile", "procfile", "vagrantfile"
        }:
            return True
        # If unknown extension or no extension, include unless identified as binary
        return bool(suffix) and suffix not in self._BINARY_EXTENSIONS

    def find_function(self, name: str, relative_path: str = ".") -> str:
        """Finds function/class definitions matching a name across files in any language."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            pattern = re.compile(
                rf"^\s*(?:(?:pub(?:lic)?|private|protected|internal|export|default|async|static|final|abstract|override|open|sealed|inline)\s+)*"
                rf"(?:def|class|function|fn|func|fun|sub|procedure|proc|struct|interface|trait|type|enum|protocol|record|actor|module|contract|const|let|var)\s+{re.escape(name)}\b",
                re.MULTILINE
            )
            results = []
            target = safe_path if safe_path.is_file() else None

            def scan(fpath: Path):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if pattern.search(line):
                                try:
                                    rel = fpath.relative_to(self.workspace_root)
                                except ValueError:
                                    rel = fpath.name if (target and target == fpath) else fpath
                                results.append(f"{rel}:{i}: {line.rstrip()}")
                except (UnicodeDecodeError, PermissionError):
                    pass

            if target:
                scan(target)
            else:
                for root, dirs, files in os.walk(safe_path):
                    dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS and not d.startswith('.')]
                    for fname in files:
                        if self._is_code_file(fname):
                            scan(Path(root) / fname)
                            if len(results) >= 50:
                                break

            if not results:
                return f"No definitions found for '{name}'."
            return f"Found {len(results)} definition(s) for '{name}':\n" + "\n".join(results)
        except Exception as e:
            return f"Error: {str(e)}"

    def find_todos(self, relative_path: str = ".") -> str:
        """Finds TODO/FIXME/HACK/XXX comments across files in any language."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            pattern = re.compile(
                r"(?:#|//|--|;|%|/\*|<!--|\bREM\b|::)\s*(TODO|FIXME|HACK|XXX|BUG|NOTE)\b.*",
                re.IGNORECASE
            )
            results = []

            def scan(fpath: Path):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            m = pattern.search(line)
                            if m:
                                try:
                                    rel = fpath.relative_to(self.workspace_root)
                                except ValueError:
                                    rel = fpath.name if safe_path.is_file() else fpath
                                results.append(f"{rel}:{i}: {line.strip()}")
                except (UnicodeDecodeError, PermissionError):
                    pass

            if safe_path.is_file():
                scan(safe_path)
            else:
                for root, dirs, files in os.walk(safe_path):
                    dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS and not d.startswith('.')]
                    for fname in files:
                        if self._is_code_file(fname):
                            scan(Path(root) / fname)
                            if len(results) >= 50:
                                break

            if not results:
                return "No TODO/FIXME/HACK comments found."
            return f"Found {len(results)} comment(s):\n" + "\n".join(results)
        except Exception as e:
            return f"Error: {str(e)}"

    def count_lines(self, relative_path: str) -> str:
        """Counts total lines, code lines, comment lines, and blank lines across any language."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_file():
                return f"Error: '{relative_path}' is not a file."

            total = code = comments = blanks = 0
            ext = safe_path.suffix.lower()
            hash_exts = {'.py', '.pyi', '.rb', '.sh', '.bash', '.zsh', '.yaml', '.yml', '.r', '.pl', '.pm', '.ex', '.exs', '.dockerfile'}
            dash_exts = {'.sql', '.psql', '.lua', '.hs', '.ada', '.vhd', '.vhdl'}
            semi_exts = {'.ini', '.asm', '.clj', '.cljs', '.lisp', '.lsp'}
            percent_exts = {'.erl', '.tex', '.prolog'}

            def is_comment(line_str: str) -> bool:
                if ext in hash_exts or safe_path.name.lower() in ("dockerfile", "makefile"):
                    return line_str.startswith("#")
                if ext in dash_exts:
                    return line_str.startswith("--")
                if ext in semi_exts:
                    return line_str.startswith(";")
                if ext in percent_exts:
                    return line_str.startswith("%")
                return line_str.startswith("//") or line_str.startswith("/*") or line_str.startswith("*")

            with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    total += 1
                    stripped = line.strip()
                    if not stripped:
                        blanks += 1
                    elif is_comment(stripped):
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
        """Lists all import/require/include/use statements across multiple languages."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_file():
                return f"Error: '{relative_path}' is not a file."

            import_pattern = re.compile(
                r"^(?:"
                r"import\s+|"
                r"from\s+.+\s+import\s+|"
                r"(?:const|let|var)\s+.+\s*=\s*require\(|"
                r"export\s+.+\s+from\s+|"
                r"#\s*include\s+[<\"]|"
                r"use\s+[\w:\\]+|"
                r"using\s+[\w.]+|"
                r"require(?:_relative)?\s*[\(\'\"]|"
                r"package\s+[\w.]+|"
                r"@import\s+|"
                r"(?:alias|require)\s+[A-Z]"
                r")"
            )

            imports = []
            with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    stripped = line.strip()
                    if import_pattern.match(stripped):
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

    async def find_symbol_definition(self, symbol_name: str, project_id: Optional[str] = None) -> str:
        """Finds exact AST definition (functions, classes, interfaces) with code snippets and line numbers."""
        from core.knowledge.code_graph import code_graph
        try:
            defs = await code_graph.get_symbol_definitions(symbol_name, project_id)
            if not defs:
                # Fallback to text matching
                return self.find_function(symbol_name)
            
            output = [f"Found {len(defs)} AST definition(s) for symbol '{symbol_name}':\n"]
            for d in defs:
                parent_info = f" (inside class {d['parent_symbol']})" if d.get('parent_symbol') else ""
                params_info = f"({', '.join(d.get('params', []))})" if d.get('params') is not None else ""
                bases_info = f" : {', '.join(d['bases'])}" if d.get('bases') else ""
                output.append(f"[{d['file_path']} L{d['start_line']}-L{d['end_line']}] [{d['kind']}] {d['name']}{params_info}{parent_info}{bases_info}")
                if d.get('docstring'):
                    output.append(f"  \"\"\"{d['docstring'].strip()}\"\"\"")
                output.append("```\n" + d['code'] + "\n```\n")
            return "\n".join(output)
        except Exception as e:
            return f"Error finding symbol definition: {str(e)}"

    async def get_class_hierarchy(self, class_name: str, project_id: Optional[str] = None) -> str:
        """Inspects superclasses, subclasses, and inheritance tree for a class."""
        from core.knowledge.code_graph import code_graph
        try:
            info = await code_graph.get_class_hierarchy(class_name, project_id)
            output = [f"🏛️ Class Hierarchy for '{class_name}':"]
            if info.get("file"):
                output.append(f"  Defined in: {info['file']}")
            if info.get("superclasses"):
                output.append(f"  Superclasses: {', '.join(info['superclasses'])}")
            else:
                output.append("  Superclasses: None (root class or unmapped)")
            if info.get("subclasses"):
                output.append(f"  Direct Subclasses ({len(info['subclasses'])}): {', '.join(info['subclasses'])}")
            if info.get("all_descendants"):
                output.append(f"  All Descendants ({len(info['all_descendants'])}): {', '.join(info['all_descendants'])}")
            return "\n".join(output)
        except Exception as e:
            return f"Error retrieving class hierarchy: {str(e)}"

    async def get_file_outline(self, file_path: str, project_id: Optional[str] = None) -> str:
        """Returns the structural outline (classes, methods, functions) of a source file."""
        from core.knowledge.code_graph import code_graph
        try:
            safe_path = self._resolve_safe_path(file_path)
            rel_path = str(safe_path.relative_to(self.workspace_root)).replace("\\", "/")
            outline = await code_graph.get_file_outline(rel_path, project_id)
            if not outline:
                return f"No symbols or structure found for '{file_path}'."
            
            lines = [f"Structure Outline for '{rel_path}':"]
            for sym in outline:
                indent = "    " if sym.get('parent') else "  "
                params = f"({', '.join(sym.get('params', []))})" if sym.get('params') is not None else ""
                lines.append(f"{indent}* [{sym['kind']}] {sym['name']}{params} (Lines {sym['start_line']}-{sym['end_line']})")
            return "\n".join(lines)
        except Exception as e:
            return f"Error extracting file outline: {str(e)}"

    async def get_symbol_callers(self, symbol_name: str, project_id: Optional[str] = None) -> str:
        """Finds all files and lines that import or invoke a symbol across the workspace."""
        from core.knowledge.code_graph import code_graph
        try:
            callers = await code_graph.get_symbol_callers(symbol_name, project_id)
            if not callers:
                return f"No callers or imports found for symbol '{symbol_name}'."
            
            lines = [f"Found {len(callers)} reference(s) to symbol '{symbol_name}':"]
            for c in callers:
                lines.append(f"  * {c['file']}:{c['line']} -> {c.get('code', c.get('caller', 'call'))}")
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


    async def find_definitions(self, symbol: str, project_id: Optional[str] = None) -> str:
        """Jump straight to the source of a type, class, or function definition."""
        return await self.find_symbol_definition(symbol, project_id)

    async def find_callers(self, function_name: str, project_id: Optional[str] = None) -> str:
        """Retrieve all call sites across the codebase before refactoring."""
        return await self.get_symbol_callers(function_name, project_id)

    async def get_module_dependencies(self, file_path: str, project_id: Optional[str] = None) -> str:
        """Inspect import/export module dependency graph for a specific file."""
        from core.knowledge.code_graph import code_graph
        try:
            safe_path = self._resolve_safe_path(file_path)
            rel_path = str(safe_path.relative_to(self.workspace_root)).replace("\\", "/")
            # A missing file has no module graph to inspect. Avoid building the
            # entire workspace index for a path that cannot have dependencies.
            res = (
                await code_graph.get_module_dependencies(rel_path, project_id)
                if safe_path.is_file()
                else {"dependencies": [], "dependents": []}
            )

            lines = [f"📦 Module Dependencies for '{rel_path}':"]
            deps = res.get("dependencies", [])
            if deps:
                lines.append(f"  Imports ({len(deps)} files):")
                for d in deps:
                    lines.append(f"    -> {d}")
            else:
                lines.append("  Imports: None detected internally.")

            dependents = res.get("dependents", [])
            if dependents:
                lines.append(f"  Imported by ({len(dependents)} files):")
                for d in dependents:
                    lines.append(f"    <- {d}")
            else:
                lines.append("  Imported by: No internal dependents.")

            return "\n".join(lines)
        except Exception as e:
            return f"Error extracting module dependencies: {str(e)}"


# Singleton
code_analysis_tools = CodeAnalysisTools()
