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
from typing import Dict, Set, Optional
from core.config import CAROLE_HOME_DIR

from core.chat.event_bus import event_bus

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
                        self.graphs[pid] = nx.node_link_graph(data)
                except Exception:
                    self.graphs[pid] = nx.DiGraph()
            else:
                self.graphs[pid] = nx.DiGraph()
        return self.graphs[pid]

    async def _save_graph(self, project_id: Optional[str]):
        try:
            graph_file = await self.get_graph_file(project_id)
            graph_file.parent.mkdir(parents=True, exist_ok=True)
            with open(graph_file, "w") as f:
                json.dump(nx.node_link_data(await self.get_graph(project_id)), f)
        except Exception as e:
            print(f"Error saving code graph for project {project_id}: {e}")

    async def mark_file_active(self, path: str, agent_name: str, project_id: Optional[str] = None):
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
        """Parses a file for dependencies and updates the graph."""
        project_root = await self.get_project_root(project_id)
        safe_path = (project_root / relative_path).resolve()
        
        graph = await self.get_graph(project_id)
        
        if not safe_path.is_file():
            if graph.has_node(relative_path):
                graph.remove_node(relative_path)
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
        
        graph.add_node(relative_path)
        
        out_edges = list(graph.out_edges(relative_path))
        graph.remove_edges_from(out_edges)
        
        for dep in dependencies:
            graph.add_edge(relative_path, dep)
            
        await self._save_graph(project_id)

    async def build_graph(self, project_id: Optional[str] = None):
        """Scans project root and maps all files."""
        project_root = await self.get_project_root(project_id)
        skip_dirs = {'.git', 'node_modules', '__pycache__', '.next', 'venv', '.venv', 'dist', 'build'}
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
            for file in files:
                if file.endswith(('.py', '.js', '.ts', '.jsx', '.tsx')):
                    full_path = Path(root) / file
                    try:
                        rel = full_path.relative_to(project_root)
                        rel_str = str(rel).replace("\\", "/")
                        await self.parse_file(rel_str, project_id)
                    except ValueError:
                        pass
        await self._save_graph(project_id)

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
