"""
# backend/core/tools/tool_registry.py

Centralized dynamic tool registry. Tools can be registered at startup from
built-in modules, external plugin files, or at runtime via the REST API.

The ToolExecutor delegates all lookups here instead of keeping a hardcoded dict.
The ReACT agent pulls the current tool descriptions from here for LLM prompts.
"""

import importlib
import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Dict, List, Optional, Any


@dataclass
class ToolSpec:
    """Metadata and handler for a single registered tool."""
    name: str
    description: str
    category: str  # filesystem, shell, git, web, browser, coordination, task, custom
    parameters: Dict[str, Any]  # simplified JSON-schema style
    permission_default: str  # "safe" | "judge" | "human"
    handler: Callable[..., Awaitable[str]]  # async (args: dict, team_id: str) -> str
    team_id: Optional[str] = None
    agent_id: Optional[str] = None


class ToolRegistry:
    """Global, mutable tool registry.  Thread-safe enough for a single
    event-loop asyncio server (no concurrent writes from multiple threads)."""

    _tools: Dict[str, ToolSpec] = {}

    # ---- core CRUD ----

    @classmethod
    def register(cls, spec: ToolSpec) -> None:
        # Validate tool name, uniqueness, and handler
        import re
        if spec.name in cls._tools:
            raise ValueError(f"Tool '{spec.name}' already registered")
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_\-]*$', spec.name):
            raise ValueError(f"Invalid tool name: {spec.name}")
        if not callable(spec.handler):
            raise ValueError(f"Handler for '{spec.name}' is not callable")
        cls._tools[spec.name] = spec

    @classmethod
    def unregister(cls, name: str) -> bool:
        return cls._tools.pop(name, None) is not None

    @classmethod
    def get(cls, name: str) -> Optional[ToolSpec]:
        return cls._tools.get(name)

    @classmethod
    def list_all(cls) -> List[ToolSpec]:
        return list(cls._tools.values())

    @classmethod
    def list_names(cls) -> List[str]:
        return list(cls._tools.keys())

    # ---- prompt generation ----

    @classmethod
    def to_llm_prompt(cls, team_id: str = None, agent_id: str = None) -> str:
        """Generates a tool description block for agent system prompts so the
        LLM knows exactly which tools it can call and how."""
        if not cls._tools:
            return ""

        lines = ["<available-tools>"]
        for spec in cls._tools.values():
            if spec.team_id is not None and spec.team_id != team_id:
                continue
            if spec.agent_id is not None and spec.agent_id != agent_id:
                continue

            params_desc = ", ".join(
                f"{k}: {v.get('type', 'string')}"
                for k, v in spec.parameters.items()
            ) if spec.parameters else "none"
            lines.append(
                f"- {spec.name}({params_desc}): {spec.description} "
                f"[category={spec.category}, permission={spec.permission_default}]"
            )
        lines.append("</available-tools>")
        return "\n".join(lines)

    # ---- plugin loading ----

    @classmethod
    def load_plugin_directory(cls, directory: str) -> int:
        """Scans *directory* for .py files, imports them, and collects any
        functions decorated with @carole_tool.  Returns count of tools loaded."""
        if not os.path.isdir(directory):
            print(f"⚠ [ToolRegistry] Plugin directory '{directory}' not found — skipping.")
            return 0

        loaded = 0
        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            filepath = os.path.join(directory, filename)
            module_name = f"plugins.{filename[:-3]}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                mod = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = mod
                spec.loader.exec_module(mod)

                # The @carole_tool decorator auto-registers, but we count
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if hasattr(attr, "_carole_tool_spec"):
                        tool_spec: ToolSpec = attr._carole_tool_spec
                        cls.register(tool_spec)
                        loaded += 1
                        print(f"  ✓ Loaded plugin tool: {tool_spec.name}")
            except Exception as e:
                print(f"  ✗ Failed to load plugin '{filename}': {e}")
        print(f"🔌 [ToolRegistry] Loaded {loaded} plugin tool(s) from '{directory}'.")
        return loaded

    @classmethod
    def to_api_list(cls) -> List[dict]:
        """Returns a JSON-serialisable list for the GET /api/tools endpoint."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "category": s.category,
                "parameters": s.parameters,
                "permission_default": s.permission_default,
            }
            for s in cls._tools.values()
        ]
