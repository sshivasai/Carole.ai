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
from core.tools.code_analysis_tools import CodeAnalysisTools

CODE_EXTENSIONS = CodeAnalysisTools._CODE_EXTENSIONS

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


def resolve_import_path(importing_file: str, raw_import: str, project_root: Path) -> List[str]:
    """
    Intelligently resolves module imports to real relative file paths in the project:
    - Python relative imports (e.g. '.models', '..utils.helpers')
    - Python package / absolute imports ('core.config', 'backend.core.models')
    - JS/TS relative imports ('./Button', '../theme', '@/components/Card')
    - JS/TS directory index files ('index.ts', 'index.tsx', 'index.js', etc.)
    - Rust relative modules ('super::models', 'crate::config')
    """
    norm_file = importing_file.replace("\\", "/")
    file_dir = posixpath.dirname(norm_file)
    clean_imp = raw_import.strip().strip("'\"`;")
    if not clean_imp:
        return []

    # Strip language keywords if raw syntax slipped through (e.g. 'import sys' -> 'sys')
    if " " in clean_imp:
        m = re.match(r"^(?:import|from|use)\s+([.\w/]+)", clean_imp)
        if m:
            clean_imp = m.group(1)
        else:
            return []

    candidates: List[str] = []

    # 1. JS / TS Relative Imports
    if clean_imp.startswith("./") or clean_imp.startswith("../"):
        base = posixpath.normpath(posixpath.join(file_dir, clean_imp))
        if posixpath.splitext(base)[1] in CODE_EXTENSIONS:
            candidates.append(base)
        else:
            candidates.extend([
                f"{base}.ts",
                f"{base}.tsx",
                f"{base}.js",
                f"{base}.jsx",
                f"{base}/index.ts",
                f"{base}/index.tsx",
                f"{base}/index.js",
                f"{base}/index.jsx"
            ])

    # 2. Python Relative Imports
    elif clean_imp.startswith("."):
        dots = len(clean_imp) - len(clean_imp.lstrip("."))
        mod_part = clean_imp.lstrip(".")
        cur_dir = file_dir
        for _ in range(dots - 1):
            cur_dir = posixpath.dirname(cur_dir)
        
        rel_target = posixpath.join(cur_dir, mod_part.replace(".", "/")) if mod_part else cur_dir
        candidates.extend([
            f"{rel_target}.py",
            f"{rel_target}/__init__.py"
        ])

    # 3. JS / TS Path Alias (@/...)
    elif clean_imp.startswith("@/"):
        sub = clean_imp[2:]
        for prefix in ("src", ""):
            base = posixpath.normpath(posixpath.join(prefix, sub)) if prefix else sub
            candidates.extend([
                f"{base}.ts",
                f"{base}.tsx",
                f"{base}.js",
                f"{base}.jsx",
                f"{base}/index.ts",
                f"{base}/index.tsx"
            ])

    # 4. Rust Super/Crate Imports
    elif "::" in clean_imp:
        parts = clean_imp.split("::")
        if parts[0] == "super":
            sub = "/".join(parts[1:])
            parent = posixpath.dirname(file_dir)
            candidates.extend([f"{parent}/{sub}.rs", f"{parent}/{sub}/mod.rs"])
        elif parts[0] == "crate":
            sub = "/".join(parts[1:])
            candidates.extend([f"src/{sub}.rs", f"src/{sub}/mod.rs"])

    # 5. Top-level / Package imports (Python / Go / etc.)
    else:
        norm_sub = clean_imp.replace(".", "/")
        candidates.extend([
            f"{norm_sub}.py",
            f"{norm_sub}/__init__.py",
            f"backend/{norm_sub}.py",
            f"backend/{norm_sub}/__init__.py",
            f"src/{norm_sub}.ts",
            f"src/{norm_sub}.tsx",
            f"{norm_sub}.ts",
            f"{norm_sub}.tsx",
            f"{norm_sub}.go",
            f"{norm_sub}.rs"
        ])

    # Verify candidates against actual filesystem
    resolved: List[str] = []
    for cand in candidates:
        cand_norm = posixpath.normpath(cand).replace("\\", "/")
        full_cand = project_root / cand_norm
        try:
            if full_cand.is_file():
                resolved.append(cand_norm)
        except Exception:
            pass

    return list(dict.fromkeys(resolved))


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
        self.inheritance_graph: Dict[str, nx.DiGraph] = {}
        self._lock = asyncio.Lock()
        
        self.start_listening_task()

    def get_inheritance_graph(self, project_id: Optional[str] = None) -> nx.DiGraph:
        pid = project_id or "default"
        if pid not in self.inheritance_graph:
            self.inheritance_graph[pid] = nx.DiGraph()
        return self.inheritance_graph[pid]

    async def get_project_root(self, project_id: Optional[str]) -> Path:
        # If an explicit custom workspace_root was provided (e.g. in tests or custom bindings)
        default_root = Path(os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[3]))).resolve()
        if self.workspace_root != default_root and self.workspace_root.exists():
            return self.workspace_root
        if project_id and project_id != "default":
            try:
                from core.tools.file_tools import file_tools
                return await file_tools.get_workspace_root(project_id)
            except Exception:
                pass
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
        project_root = await self.get_project_root(project_id)
        if pid not in self.graphs:
            graph_file = await self.get_graph_file(project_id)
            if graph_file.exists():
                try:
                    with open(graph_file, "r") as f:
                        data = json.load(f)
                        g = nx.node_link_graph(data, edges="links")
                        self.graphs[pid] = g
                except Exception:
                    self.graphs[pid] = nx.DiGraph()
            else:
                self.graphs[pid] = nx.DiGraph()

        g = self.graphs[pid]
        # Prune phantom nodes: files that are untracked or do not exist on disk
        if project_root.exists():
            phantom_nodes = [
                n for n in list(g.nodes)
                if not is_tracked_code_file(str(n)) or not (project_root / str(n)).is_file()
            ]
            if phantom_nodes:
                g.remove_nodes_from(phantom_nodes)
                for p in phantom_nodes:
                    self._remove_file_from_index(str(p), pid)
                try:
                    graph_file = await self.get_graph_file(project_id)
                    with open(graph_file, "w") as f:
                        json.dump(nx.node_link_data(g, edges="links"), f)
                except Exception:
                    pass

        return self.graphs[pid]

    async def _save_graph(self, project_id: Optional[str]):
        try:
            graph_file = await self.get_graph_file(project_id)
            graph_file.parent.mkdir(parents=True, exist_ok=True)
            pid = project_id or "default"
            g = self.graphs.get(pid)
            if g is None:
                g = await self.get_graph(project_id)
            with open(graph_file, "w") as f:
                json.dump(nx.node_link_data(g, edges="links"), f)
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

        inh_graph = self.get_inheritance_graph(pid)

        for chunk in chunks:
            # Map simple symbol -> AST chunk
            if chunk.name not in self.symbol_index[pid]:
                self.symbol_index[pid][chunk.name] = []
            self.symbol_index[pid][chunk.name].append(chunk)

            # Map qualified symbol (Parent.child) -> AST chunk
            if chunk.parent_symbol:
                qual_name = f"{chunk.parent_symbol}.{chunk.name}"
                if qual_name not in self.symbol_index[pid]:
                    self.symbol_index[pid][qual_name] = []
                self.symbol_index[pid][qual_name].append(chunk)

            # Map class inheritance
            if chunk.kind == "class" and getattr(chunk, "bases", None):
                inh_graph.add_node(chunk.name, file=relative_path)
                for b in chunk.bases:
                    inh_graph.add_edge(chunk.name, b)

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
            resolved = resolve_import_path(relative_path, imp, project_root)
            for r in resolved:
                if r != relative_path and is_tracked_code_file(r):
                    dependencies.add(r)

        graph.add_node(relative_path)
        out_edges = list(graph.out_edges(relative_path))
        graph.remove_edges_from(out_edges)
        for dep in dependencies:
            graph.add_edge(relative_path, dep)

        # 4. Notify hybrid search incrementally
        try:
            from core.knowledge.hybrid_search import hybrid_code_search
            hybrid_code_search.update_file_chunks(project_id, relative_path, chunks, content=content)
        except Exception:
            pass
            
        await self._save_graph(project_id)

    def _remove_file_from_index(self, relative_path: str, pid: str):
        """Clean old AST chunks when a file is re-parsed."""
        old_chunks = self.file_chunks.get(pid, {}).pop(relative_path, [])
        for c in old_chunks:
            if c.name in self.symbol_index.get(pid, {}):
                self.symbol_index[pid][c.name] = [
                    x for x in self.symbol_index[pid][c.name] if x.file_path != relative_path
                ]
                if not self.symbol_index[pid][c.name]:
                    del self.symbol_index[pid][c.name]
            if c.parent_symbol:
                qual_name = f"{c.parent_symbol}.{c.name}"
                if qual_name in self.symbol_index.get(pid, {}):
                    self.symbol_index[pid][qual_name] = [
                        x for x in self.symbol_index[pid][qual_name] if x.file_path != relative_path
                    ]
                    if not self.symbol_index[pid][qual_name]:
                        del self.symbol_index[pid][qual_name]
            for called in c.calls:
                if called in self.call_hierarchy.get(pid, {}):
                    self.call_hierarchy[pid][called] = [
                        x for x in self.call_hierarchy[pid][called] if x["file"] != relative_path
                    ]
            if c.kind == "class" and pid in self.inheritance_graph:
                if self.inheritance_graph[pid].has_node(c.name):
                    self.inheritance_graph[pid].remove_node(c.name)

        try:
            from core.knowledge.hybrid_search import hybrid_code_search
            hybrid_code_search.remove_file(pid, relative_path)
        except Exception:
            pass

    async def build_graph(self, project_id: Optional[str] = None):
        """Scans project root and maps all code files into AST index."""
        project_root = await self.get_project_root(project_id)
        existing_on_disk: Set[str] = set()
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not any(ign in d for ign in IGNORE_DIR_SUBSTRINGS) and not d.startswith('.')]
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in CODE_EXTENSIONS:
                    full_path = Path(root) / file
                    try:
                        rel = full_path.relative_to(project_root)
                        rel_str = str(rel).replace("\\", "/")
                        existing_on_disk.add(rel_str)
                        await self.parse_file(rel_str, project_id)
                    except ValueError:
                        pass

        # Prune any nodes in graph that are no longer on disk
        graph = await self.get_graph(project_id)
        pid = project_id or "default"
        stale_nodes = [n for n in list(graph.nodes) if n not in existing_on_disk]
        for stale in stale_nodes:
            graph.remove_node(stale)
            self._remove_file_from_index(stale, pid)

        await self._save_graph(project_id)

    async def get_symbol_definitions(self, symbol_name: str, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Instant O(1) AST lookup for symbol definitions (supports simple and qualified names)."""
        pid = project_id or "default"
        if pid not in self.symbol_index:
            await self.build_graph(project_id)
        
        # 1. Direct match (simple name or pre-indexed qualified name)
        chunks = self.symbol_index.get(pid, {}).get(symbol_name, [])
        if chunks:
            return [c.to_dict() for c in chunks]

        # 2. Qualified search fallback if "." in symbol_name (e.g. "WorkflowEngine.execute")
        if "." in symbol_name:
            parts = symbol_name.split(".", 1)
            parent, child = parts[0], parts[1]
            candidates = self.symbol_index.get(pid, {}).get(child, [])
            matched = [c for c in candidates if c.parent_symbol == parent]
            if matched:
                return [c.to_dict() for c in matched]

        return []

    async def get_class_hierarchy(self, class_name: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """Returns inheritance hierarchy (superclasses and known subclasses) for a class."""
        pid = project_id or "default"
        if pid not in self.symbol_index:
            await self.build_graph(project_id)

        inh = self.get_inheritance_graph(pid)
        superclasses: List[str] = []
        subclasses: List[str] = []

        if inh.has_node(class_name):
            superclasses = list(inh.successors(class_name))
            subclasses = list(inh.predecessors(class_name))

        defs = self.symbol_index.get(pid, {}).get(class_name, [])
        class_chunks = [c for c in defs if c.kind == "class"]
        file_path = class_chunks[0].file_path if class_chunks else None

        return {
            "class": class_name,
            "file": file_path,
            "superclasses": superclasses,
            "subclasses": subclasses,
            "all_ancestors": list(nx.descendants(inh, class_name)) if inh.has_node(class_name) else [],
            "all_descendants": list(nx.ancestors(inh, class_name)) if inh.has_node(class_name) else []
        }

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

    async def generate_repo_map(
        self,
        project_id: Optional[str] = None,
        max_tokens: int = 800,
        focus_files: Optional[List[str]] = None
    ) -> str:
        """Generates a compact, PageRank-weighted structural repository map.

        Inspired by Aider's Tree-Sitter + PageRank context budgeting:
        - Extracts key classes, functions, and method signatures without function bodies.
        - Ranks files and symbols by NetworkX PageRank centrality (most imported/referenced).
        - Enforces a strict token budget (default 800 tokens) so agent context is never flooded.
        """
        pid = project_id or "default"
        if pid not in self.file_chunks or not self.file_chunks[pid]:
            await self.build_graph(project_id)

        file_chunks_map = self.file_chunks.get(pid, {})
        if not file_chunks_map:
            return ""

        graph = await self.get_graph(project_id)

        # Calculate PageRank scores across the dependency graph
        pagerank_scores: Dict[str, float] = {}
        if len(graph) > 1 and graph.number_of_edges() > 0:
            try:
                personalization = None
                if focus_files:
                    norm_focus = [f.replace("\\", "/") for f in focus_files]
                    matched_focus = [f for f in norm_focus if f in graph]
                    if matched_focus:
                        personalization = {n: (10.0 if n in matched_focus else 1.0) for n in graph.nodes()}
                        total = sum(personalization.values())
                        personalization = {k: v / total for k, v in personalization.items()}

                pagerank_scores = nx.pagerank(graph, alpha=0.85, max_iter=100, personalization=personalization)
            except Exception:
                pagerank_scores = {node: 1.0 / len(graph) for node in graph.nodes()}
        else:
            pagerank_scores = {node: 1.0 for node in graph.nodes()}

        # Sort files by PageRank score descending
        ranked_files = sorted(
            file_chunks_map.keys(),
            key=lambda f: pagerank_scores.get(f, 0.0),
            reverse=True
        )

        lines = ["<repo-map>"]
        max_chars = max_tokens * 4
        current_chars = len(lines[0])

        for file_path in ranked_files:
            chunks = file_chunks_map[file_path]
            if not chunks:
                continue

            file_header = f"{file_path}:"
            file_lines = [file_header]

            for chunk in chunks:
                sig = ""
                code = chunk.code.strip()
                if chunk.kind in ("class", "function", "method"):
                    first_line = code.splitlines()[0].strip() if code else ""
                    if first_line:
                        indent = "  " if chunk.kind in ("class", "function") else "    "
                        sig = f"{indent}{first_line}"
                elif chunk.kind in ("interface", "type"):
                    first_line = code.splitlines()[0].strip() if code else ""
                    if first_line:
                        sig = f"  {first_line}"

                if sig:
                    file_lines.append(sig)

            # Only include file if it had definitions
            if len(file_lines) > 1:
                file_block = "\n".join(file_lines)
                if current_chars + len(file_block) + 2 > max_chars:
                    # Truncate to stay strictly under the token budget
                    break
                lines.append(file_block)
                current_chars += len(file_block) + 2

        lines.append("</repo-map>")
        if len(lines) <= 2:
            return ""

        return "\n".join(lines)

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
