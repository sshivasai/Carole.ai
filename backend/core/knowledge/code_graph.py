"""
# backend/core/knowledge/code_graph.py

Compiler-grade Code Knowledge Graph and AST Symbol Index.
Tracks cross-file dependencies, symbol definitions, call hierarchies, and active file editor locks.
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
from core.knowledge.ast_parser import parse_file_ast, ASTChunk

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
        
        # AST-Aware In-Memory Indexes (project_id -> dict)
        self.symbol_index: Dict[str, Dict[str, List[ASTChunk]]] = {}
        self.file_chunks: Dict[str, Dict[str, List[ASTChunk]]] = {}
        self.call_hierarchy: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
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
        """Parses a code file using the AST parser, updating the graph & symbol index."""
        pid = project_id or "default"
        if pid not in self.symbol_index:
            self.symbol_index[pid] = {}
            self.file_chunks[pid] = {}
            self.call_hierarchy[pid] = {}

        if not is_tracked_code_file(relative_path):
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
            # Clean index
            self._remove_file_from_index(relative_path, pid)
            return

        try:
            with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return

        # 1. Parse AST Symbols & Imports
        chunks, raw_imports = parse_file_ast(content, relative_path)
        
        # 2. Update File Chunks & Symbol Index
        self._remove_file_from_index(relative_path, pid)
        self.file_chunks[pid][relative_path] = chunks

        for chunk in chunks:
            # Map symbol -> AST chunk
            if chunk.name not in self.symbol_index[pid]:
                self.symbol_index[pid][chunk.name] = []
            self.symbol_index[pid][chunk.name].append(chunk)

            # Map called function -> caller
            for called in chunk.calls:
                if called not in self.call_hierarchy[pid]:
                    self.call_hierarchy[pid][called] = []
                self.call_hierarchy[pid][called].append({
                    "file": relative_path,
                    "line": chunk.start_line,
                    "caller": chunk.name,
                    "caller_kind": chunk.kind,
                    "code": f"{chunk.kind} {chunk.name}() calls {called}()"
                })

        # 3. Resolve file dependencies for NetworkX graph
        dependencies = set()
        for imp in raw_imports:
            norm_imp = imp.replace(".", "/")
            dependencies.add(f"{norm_imp}.py")
            dependencies.add(f"{norm_imp}.ts")
            dependencies.add(f"{norm_imp}.tsx")
            dependencies.add(f"{norm_imp}.js")
            dependencies.add(f"{norm_imp}/index.ts")

        graph.add_node(relative_path)
        out_edges = list(graph.out_edges(relative_path))
        graph.remove_edges_from(out_edges)
        for dep in dependencies:
            graph.add_edge(relative_path, dep)
            
        await self._save_graph(project_id)

    def _remove_file_from_index(self, relative_path: str, pid: str):
        """Clean old AST chunks when a file is re-parsed."""
        old_chunks = self.file_chunks.get(pid, {}).pop(relative_path, [])
        for c in old_chunks:
            if c.name in self.symbol_index.get(pid, {}):
                self.symbol_index[pid][c.name] = [
                    x for x in self.symbol_index[pid][c.name] if x.file_path != relative_path
                ]
            for called in c.calls:
                if called in self.call_hierarchy.get(pid, {}):
                    self.call_hierarchy[pid][called] = [
                        x for x in self.call_hierarchy[pid][called] if x["file"] != relative_path
                    ]

    async def build_graph(self, project_id: Optional[str] = None):
        """Scans project root and maps all code files into AST index."""
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

    async def get_symbol_definitions(self, symbol_name: str, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Instant O(1) AST lookup for symbol definitions."""
        pid = project_id or "default"
        if pid not in self.symbol_index:
            await self.build_graph(project_id)
        
        chunks = self.symbol_index.get(pid, {}).get(symbol_name, [])
        return [c.to_dict() for c in chunks]

    async def get_file_outline(self, file_path: str, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns structural outline of classes, functions, and methods in a file."""
        pid = project_id or "default"
        norm_path = file_path.replace("\\", "/")
        if pid not in self.file_chunks or norm_path not in self.file_chunks[pid]:
            await self.parse_file(norm_path, project_id)

        chunks = self.file_chunks.get(pid, {}).get(norm_path, [])
        return [
            {
                "name": c.name,
                "kind": c.kind,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "parent": c.parent_symbol,
                "params": c.params
            }
            for c in chunks
        ]

    async def get_symbol_callers(self, symbol_name: str, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Instant O(1) AST lookup for callers of any function or class."""
        pid = project_id or "default"
        if pid not in self.call_hierarchy:
            await self.build_graph(project_id)

        callers = self.call_hierarchy.get(pid, {}).get(symbol_name, [])
        if callers:
            return callers[:50]

        # Fallback regex scan if symbol was dynamically imported/invoked
        project_root = await self.get_project_root(project_id)
        fallback_callers = []
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
                                    fallback_callers.append({
                                        "file": rel,
                                        "line": idx,
                                        "caller": "global",
                                        "caller_kind": "expression",
                                        "code": line.strip()
                                    })
                                    if len(fallback_callers) >= 40:
                                        break
                    except Exception:
                        pass
        return fallback_callers

    async def get_symbol_callees(self, function_name: str, file_path: str, project_id: Optional[str] = None) -> List[str]:
        """Finds all function calls invoked within a specific function/class definition."""
        pid = project_id or "default"
        norm_path = file_path.replace("\\", "/")
        if pid not in self.file_chunks or norm_path not in self.file_chunks[pid]:
            await self.parse_file(norm_path, project_id)

        chunks = self.file_chunks.get(pid, {}).get(norm_path, [])
        for c in chunks:
            if c.name == function_name:
                return c.calls

        return []

    async def get_module_dependencies(self, file_path: str, project_id: Optional[str] = None) -> Dict[str, List[str]]:
        """Returns direct imports (dependencies) and modules that import this file (dependents)."""
        norm_path = file_path.replace("\\", "/").strip("/")
        graph = await self.get_graph(project_id)
        if not graph.has_node(norm_path):
            await self.parse_file(norm_path, project_id)
            graph = await self.get_graph(project_id)

        dependencies = list(graph.successors(norm_path)) if graph.has_node(norm_path) else []
        dependents = list(graph.predecessors(norm_path)) if graph.has_node(norm_path) else []
        return {
            "file": norm_path,
            "dependencies": dependencies,
            "dependents": dependents,
        }

    async def get_all_chunks(self, project_id: Optional[str] = None) -> List[ASTChunk]:
        """Returns all parsed ASTChunk objects across all workspace files."""
        pid = project_id or "default"
        if pid not in self.file_chunks:
            await self.build_graph(project_id)
        all_c = []
        for chunks in self.file_chunks.get(pid, {}).values():
            all_c.extend(chunks)
        return all_c

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
