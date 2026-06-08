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
from typing import Dict, Set

from core.chat.event_bus import event_bus

class CodeGraph:
    def __init__(self, workspace_root: str = None):
        if not workspace_root:
            workspace_root = os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[3]))
        self.workspace_root = Path(workspace_root).resolve()
        
        self.graph_file = Path(".carole/code_graph.json")
        os.makedirs(".carole", exist_ok=True)
        
        if self.graph_file.exists():
            try:
                with open(self.graph_file, "r") as f:
                    data = json.load(f)
                    self.graph = nx.node_link_graph(data)
            except Exception:
                self.graph = nx.DiGraph()
        else:
            self.graph = nx.DiGraph()
            
        self.active_editors: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()
        
        # Build initial graph synchronously or kick off task
        if not self.graph_file.exists():
            self.build_graph()
            
        self.start_listening_task()

    def _save_graph(self):
        try:
            with open(self.graph_file, "w") as f:
                json.dump(nx.node_link_data(self.graph), f)
        except Exception as e:
            print(f"Error saving code graph: {e}")

    def mark_file_active(self, path: str, agent_name: str):
        if path not in self.active_editors:
            self.active_editors[path] = set()
        self.active_editors[path].add(agent_name)
        self._save_graph()
        
    def clear_file_active(self, path: str):
        if path in self.active_editors:
            self.active_editors.pop(path, None)
            self._save_graph()

    def parse_file(self, relative_path: str):
        """Parses a file for dependencies and updates the graph."""
        safe_path = (self.workspace_root / relative_path).resolve()
        if not safe_path.is_file():
            if self.graph.has_node(relative_path):
                self.graph.remove_node(relative_path)
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
                    
        elif safe_path.suffix in (".js", ".ts", ".jsx", ".tsx"):
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
        
        # We only keep edges where the dependency actually exists in the workspace
        # But for simplicity, we can just add the edge. Later we can filter valid nodes.
        self.graph.add_node(relative_path)
        
        out_edges = list(self.graph.out_edges(relative_path))
        self.graph.remove_edges_from(out_edges)
        
        for dep in dependencies:
            self.graph.add_edge(relative_path, dep)
            
        self._save_graph()

    def build_graph(self):
        """Scans WORKSPACE_ROOT and maps all files."""
        skip_dirs = {'.git', 'node_modules', '__pycache__', '.next', 'venv', '.venv', 'dist', 'build'}
        for root, dirs, files in os.walk(self.workspace_root):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
            for file in files:
                if file.endswith(('.py', '.js', '.ts', '.jsx', '.tsx')):
                    full_path = Path(root) / file
                    try:
                        rel = full_path.relative_to(self.workspace_root)
                        # Normalize backslash to forward slash for posixpath consistency
                        rel_str = str(rel).replace("\\", "/")
                        self.parse_file(rel_str)
                    except ValueError:
                        pass
        self._save_graph()

    async def _listen_for_file_changes(self):
        queue = await event_bus.subscribe("system:file_changes")
        while True:
            try:
                event = await queue.get()
                if event.get("type") == "file_change":
                    path = event.get("path")
                    if path:
                        path = path.replace("\\", "/")
                        self.parse_file(path)
            except Exception as e:
                print(f"Error in CodeGraph listener: {e}")

    def start_listening_task(self):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._listen_for_file_changes())
        except RuntimeError:
            # No running loop, maybe we're just importing
            pass

code_graph = CodeGraph()
