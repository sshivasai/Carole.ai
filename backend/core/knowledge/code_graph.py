"""
# backend/core/knowledge/code_graph.py

Real-time Code Knowledge Graph for tracking dependencies and active file editors.
"""

import os
import re
import json
import posixpath
from pathlib import Path
import asyncio
import networkx as nx
from typing import Dict, Set, Optional, List, Any
from core.config import CAROLE_HOME_DIR

from core.chat.event_bus import event_bus

CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".rb", ".php", ".swift", ".kt", ".scala", ".vue", ".svelte"
}

IGNORE_DIR_SUBSTRINGS = {
    ".carole", "scratchpads", ".git", "node_modules", "__pycache__",
    ".next", "venv", ".venv", "dist", "build", ".cache"
}

def is_tracked_code_file(path_str: str) -> bool:
    """Returns True only for real source code files, ignoring scratchpads and system dirs."""
    norm = path_str.replace("\\", "/").strip("/")
    parts = norm.split("/")
    for p in parts:
        if p in IGNORE_DIR_SUBSTRINGS or (p.startswith(".") and p != "."):
            return False
    ext = posixpath.splitext(norm)[1].lower()
    return ext in CODE_EXTENSIONS

class CodeGraph:
    def __init__(self, workspace_root: str = None):
        if not workspace_root:
            workspace_root = os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[3]))
        self.workspace_root = Path(workspace_root).resolve()
        
        self.graphs: Dict[str, nx.DiGraph] = {}
        self.active_editors: Dict[str, Dict[str, Set[str]]] = {}
        self._lock = asyncio.Lock()
        
        self.start_listening_task()

    async def get_project_root(self, project_id: Optional[str]) -> Path:
        if project_id:
            from core.tools.file_tools import file_tools
            return await file_tools.get_workspace_root(project_id)
        return self.workspace_root

    async def get_graph_file(self, project_id: Optional[str]) -> Path:
        if project_id:
            root = await self.get_project_root(project_id)
            carole_dir = root / ".carole"
            carole_dir.mkdir(parents=True, exist_ok=True)
            return carole_dir / "code_graph.json"
        return CAROLE_HOME_DIR / "code_graph.json"

    async def get_graph(self, project_id: Optional[str]) -> nx.DiGraph:
        pid = project_id or "default"
        if pid not in self.graphs:
            graph_file = await self.get_graph_file(project_id)
            if graph_file.exists():
                try:
                    with open(graph_file, "r") as f:
                        data = json.load(f)
                        g = nx.node_link_graph(data)
                        # Clean out any non-code or scratchpad nodes from legacy saves
                        invalid_nodes = [n for n in g.nodes if not is_tracked_code_file(str(n))]
                        if invalid_nodes:
                            g.remove_nodes_from(invalid_nodes)
                        self.graphs[pid] = g
                except Exception:
                    self.graphs[pid] = nx.DiGraph()
            else:
                self.graphs[pid] = nx.DiGraph()
        return self.graphs[pid]

    async def _save_graph(self, project_id: Optional[str]):
        try:
            graph_file = await self.get_graph_file(project_id)
            graph_file.parent.mkdir(parents=True, exist_ok=True)
            g = await self.get_graph(project_id)
            with open(graph_file, "w") as f:
                json.dump(nx.node_link_data(g), f)
        except Exception as e:
            print(f"Error saving code graph for project {project_id}: {e}")

    async def mark_file_active(self, path: str, agent_name: str, project_id: Optional[str] = None):
        if not is_tracked_code_file(path):
            return
        pid = project_id or "default"
        if pid not in self.active_editors:
            self.active_editors[pid] = {}
        if path not in self.active_editors[pid]:
            self.active_editors[pid][path] = set()
        self.active_editors[pid][path].add(agent_name)
        await self._save_graph(project_id)
        
    async def clear_file_active(self, path: str, project_id: Optional[str] = None):
        pid = project_id or "default"
        if pid in self.active_editors and path in self.active_editors[pid]:
            self.active_editors[pid].pop(path, None)
            await self._save_graph(project_id)

    async def parse_file(self, relative_path: str, project_id: Optional[str] = None):
        """Parses a code file for dependencies and updates the graph."""
        if not is_tracked_code_file(relative_path):
            # If an ignored/non-code file was previously added, remove it from graph
            graph = await self.get_graph(project_id)
            if graph.has_node(relative_path):
                graph.remove_node(relative_path)
                await self._save_graph(project_id)
            return

        project_root = await self.get_project_root(project_id)
        safe_path = (project_root / relative_path).resolve()
        
        graph = await self.get_graph(project_id)
        
        if not safe_path.is_file():
            if graph.has_node(relative_path):
                graph.remove_node(relative_path)
                await self._save_graph(project_id)
            return

        try:
            with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return

        dependencies = set()
        
        if safe_path.suffix == ".py":
            import_pattern = re.compile(r"^\s*(?:import|from)\s+([\.a-zA-Z0-9_]+)", re.MULTILINE)
            for match in import_pattern.findall(content):
                if match.startswith("."):
                    # relative import
                    dots = len(match) - len(match.lstrip("."))
                    base_dir = posixpath.dirname(relative_path)
                    for _ in range(dots - 1):
                        base_dir = posixpath.dirname(base_dir)
                    mod_name = match.lstrip(".")
                    if mod_name:
                        resolved_mod = posixpath.join(base_dir, mod_name.replace(".", "/"))
                    else:
                        resolved_mod = base_dir
                    dependencies.add(f"{resolved_mod}.py")
                    dependencies.add(f"{resolved_mod}/__init__.py")
                else:
                    # absolute module
                    mod_path = match.replace(".", "/")
                    dependencies.add(f"{mod_path}.py")
                    dependencies.add(f"{mod_path}/__init__.py")
                    dependencies.add(f"backend/{mod_path}.py")
                    dependencies.add(f"backend/{mod_path}/__init__.py")
                    dependencies.add(f"src/{mod_path}.py")
                    dependencies.add(f"src/{mod_path}/__init__.py")
                    
        elif safe_path.suffix in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"):
            import_pattern = re.compile(r"(?:import|require)\s*\(?\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
            for match in import_pattern.findall(content):
                if match.startswith("./") or match.startswith("../"):
                    base_dir = posixpath.dirname(relative_path)
                    resolved_mod = posixpath.normpath(posixpath.join(base_dir, match))
                    dependencies.add(resolved_mod + ".ts")
                    dependencies.add(resolved_mod + ".tsx")
                    dependencies.add(resolved_mod + ".js")
                    dependencies.add(resolved_mod + ".jsx")
                    dependencies.add(resolved_mod + "/index.ts")
                    dependencies.add(resolved_mod + "/index.js")
                    dependencies.add(resolved_mod)
        
        graph.add_node(relative_path)
        
        out_edges = list(graph.out_edges(relative_path))
        graph.remove_edges_from(out_edges)
        
        for dep in dependencies:
            graph.add_edge(relative_path, dep)
            
        await self._save_graph(project_id)

    async def build_graph(self, project_id: Optional[str] = None):
        """Scans project root and maps all code files."""
        project_root = await self.get_project_root(project_id)
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not any(ign in d for ign in IGNORE_DIR_SUBSTRINGS) and not d.startswith('.')]
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in CODE_EXTENSIONS:
                    full_path = Path(root) / file
                    try:
                        rel = full_path.relative_to(project_root)
                        rel_str = str(rel).replace("\\", "/")
                        await self.parse_file(rel_str, project_id)
                    except ValueError:
                        pass
        await self._save_graph(project_id)

    async def get_symbol_callers(self, symbol_name: str, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Finds all files and lines that import or invoke a symbol across the project."""
        project_root = await self.get_project_root(project_id)
        callers = []
        pattern = re.compile(rf"\b{re.escape(symbol_name)}\s*\(|\bimport\s+.*?\b{re.escape(symbol_name)}\b", re.MULTILINE)
        
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not any(ign in d for ign in IGNORE_DIR_SUBSTRINGS) and not d.startswith('.')]
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in CODE_EXTENSIONS:
                    fpath = Path(root) / file
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            for idx, line in enumerate(f, 1):
                                if pattern.search(line):
                                    rel = str(fpath.relative_to(project_root)).replace("\\", "/")
                                    callers.append({
                                        "file": rel,
                                        "line": idx,
                                        "code": line.strip()
                                    })
                                    if len(callers) >= 40:
                                        break
                    except Exception:
                        pass
        return callers

    async def get_symbol_callees(self, function_name: str, file_path: str, project_id: Optional[str] = None) -> List[str]:
        """Finds all function calls invoked within a specific function/class definition."""
        project_root = await self.get_project_root(project_id)
        safe_path = (project_root / file_path).resolve()
        if not safe_path.is_file():
            return []

        try:
            with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
                code = f.read()

            callees = set()
            if safe_path.suffix == ".py":
                import ast
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
                        for subnode in ast.walk(node):
                            if isinstance(subnode, ast.Call):
                                if isinstance(subnode.func, ast.Name):
                                    callees.add(subnode.func.id)
                                elif isinstance(subnode.func, ast.Attribute):
                                    callees.add(subnode.func.attr)
            else:
                # Regex call extractor for JS/TS
                call_pattern = re.compile(r"\b([a-zA-Z_]\w+)\s*\(")
                for match in call_pattern.findall(code):
                    if match not in ("if", "for", "while", "switch", "catch", "function", function_name):
                        callees.add(match)

            return sorted(list(callees))[:30]
        except Exception:
            return []

    async def _listen_for_file_changes(self):
        queue = await event_bus.subscribe("system:file_changes")
        while True:
            try:
                event = await queue.get()
                if event.get("type") == "file_change":
                    path = event.get("path")
                    project_id = event.get("project_id")
                    if path:
                        path = path.replace("\\", "/")
                        await self.parse_file(path, project_id)
            except Exception as e:
                print(f"Error in CodeGraph listener: {e}")

    def start_listening_task(self):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._listen_for_file_changes())
        except RuntimeError:
            pass

code_graph = CodeGraph()
