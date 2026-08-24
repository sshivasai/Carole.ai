"""
# backend/core/tools/tool_registry.py

Centralized dynamic tool registry. Tools can be registered at startup from
built-in modules, external plugin files, or at runtime via the REST API.

The ToolExecutor delegates all lookups here instead of keeping a hardcoded dict.
The ReACT agent pulls the current tool descriptions from here for LLM prompts.

Plugin discovery:
  Each plugin module MAY set a module-level list `__carole_tools__` containing
  the ToolSpec objects it wants to export.  If the list is present the loader
  uses it directly (O(1)).  Otherwise it falls back to scanning all module
  attributes for `_carole_tool_spec` markers (legacy O(n) path).

  Plugins can use the `carole_tool` decorator (defined below) to populate
  `__carole_tools__` automatically.
"""

import importlib
import importlib.util
import logging
import os
import sys
from dataclasses import dataclass
from typing import Callable, Awaitable, Dict, List, Optional, Any

logger = logging.getLogger("carole.tool_registry")


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
    def register(cls, spec: ToolSpec, force: bool = False) -> None:
        # Validate tool name, uniqueness, and handler
        import re
        if spec.name in cls._tools:
            if force:
                # Silent idempotent re-registration (e.g., plugin hot-reload)
                cls._tools[spec.name] = spec
                return
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

            # Keep description concise (first sentence/line)
            raw_desc = (spec.description or "").strip().split("\n")[0].strip()
            if len(raw_desc) > 180:
                raw_desc = raw_desc[:177] + "..."

            if spec.parameters:
                param_parts = []
                for k, v in spec.parameters.items():
                    param_type = v.get("type", "string")
                    required = v.get("required", False)
                    desc = v.get("description", "")
                    entry = f'"{k}": {param_type}' + (" (required)" if required else "")
                    if desc:
                        # Include concise description if under 60 chars, or trim
                        clean_desc = desc.split("\n")[0].strip()
                        if len(clean_desc) > 60:
                            clean_desc = clean_desc[:57] + "..."
                        entry += f' /* {clean_desc} */'
                    param_parts.append(entry)
                params_desc = "{" + ", ".join(param_parts) + "}"
            else:
                params_desc = "{}"

            lines.append(
                f"- {spec.name}({params_desc}): {raw_desc} [category={spec.category}, permission={spec.permission_default}]"
            )
        lines.append("</available-tools>")
        return "\n".join(lines)

    @classmethod
    def to_function_schemas(cls, team_id: str = None, agent_id: str = None) -> List[dict]:
        """Returns an OpenAI-spec 'tools' array for native function calling.

        Each entry follows the format:
          {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}
        """
        schemas = []
        for spec in cls._tools.values():
            if spec.team_id is not None and spec.team_id != team_id:
                continue
            if spec.agent_id is not None and spec.agent_id != agent_id:
                continue

            description = spec.description
            if spec.name == "browser_navigate":
                try:
                    from core.llm.config_manager import load_config
                    provider = load_config().get("browser_automation", {}).get("provider", "local")
                    if provider != "local":
                        description += f" (Note: Anti-bot and CAPTCHA bypassing is currently ENABLED via {provider.capitalize()})."
                except Exception:
                    pass

            # Build a minimal JSON-Schema object from spec.parameters
            properties = {}
            required = []
            for param_name, param_info in (spec.parameters or {}).items():
                properties[param_name] = {
                    "type": param_info.get("type", "string"),
                    "description": param_info.get("description", ""),
                }
                if param_info.get("required", False):
                    required.append(param_name)

            schemas.append({
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": f"{description} [category={spec.category}, permission={spec.permission_default}]",
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            })
        return schemas

    # ---- plugin loading ----

    @classmethod
    def load_plugin_directory(cls, directory: str) -> int:
        """Scans *directory* for .py files, imports them, and registers any
        ToolSpecs they export via the `__carole_tools__` list or the
        `@carole_tool` decorator.  Returns count of tools loaded.

        Fast path (O(1) per module):
          The module defines `__carole_tools__ = [spec1, spec2, ...]`.
          The loader reads the list directly — no attribute scanning required.

        Legacy fallback (O(n) per module):
          If `__carole_tools__` is absent the loader scans all module attributes
          for `._carole_tool_spec` markers (backward-compatible with old plugins).
        """
        if not os.path.isdir(directory):
            logger.warning("[ToolRegistry] Plugin directory '%s' not found — skipping.", directory)
            return 0

        loaded = 0
        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            filepath = os.path.join(directory, filename)
            module_name = f"plugins.{filename[:-3]}"
            try:
                mod_spec = importlib.util.spec_from_file_location(module_name, filepath)
                mod = importlib.util.module_from_spec(mod_spec)
                sys.modules[module_name] = mod
                mod_spec.loader.exec_module(mod)

                # ── Fast path: module explicitly lists its tools ──────────────
                if hasattr(mod, "__carole_tools__"):
                    tool_specs: List[ToolSpec] = mod.__carole_tools__
                    for tool_spec in tool_specs:
                        try:
                            cls.register(tool_spec, force=False)
                            logger.info("  ✓ Loaded plugin tool: %s (from __carole_tools__)", tool_spec.name)
                            loaded += 1
                        except ValueError as dup:
                            logger.debug("  ~ Plugin tool skipped (already registered): %s — %s", tool_spec.name, dup)

                else:
                    # ── Legacy fallback: scan all attributes for marker ───────
                    for attr_name in dir(mod):
                        attr = getattr(mod, attr_name, None)
                        if attr is None:
                            continue
                        tool_spec = getattr(attr, "_carole_tool_spec", None)
                        if isinstance(tool_spec, ToolSpec):
                            try:
                                cls.register(tool_spec, force=False)
                                logger.info("  ✓ Loaded plugin tool: %s (legacy scan)", tool_spec.name)
                                loaded += 1
                            except ValueError as dup:
                                logger.debug("  ~ Plugin tool skipped: %s — %s", tool_spec.name, dup)

            except Exception as e:
                logger.exception("  ✗ Failed to load plugin '%s': %s", filename, e)

        logger.info("🔌 [ToolRegistry] Loaded %d plugin tool(s) from '%s'.", loaded, directory)
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


# ─── Plugin Decorator ────────────────────────────────────────────────────────

def carole_tool(
    name: str,
    description: str,
    category: str = "custom",
    parameters: Optional[Dict[str, Any]] = None,
    permission_default: str = "safe",
    team_id: Optional[str] = None,
    agent_id: Optional[str] = None,
):
    """Decorator for plugin tool functions.  Populates the module-level
    ``__carole_tools__`` list so the O(1) fast-path loader can find tools
    without scanning all module attributes.

    Usage in a plugin file::

        from core.tools.tool_registry import carole_tool

        @carole_tool(
            name="my_tool",
            description="Does something useful.",
            category="custom",
            parameters={"value": {"type": "string", "description": "The input value."}},
            permission_default="safe",
        )
        async def my_tool(args: dict, team_id: str) -> str:
            return f"Got: {args.get('value')}"

        # The decorator auto-registers this into __carole_tools__ for fast loading.
    """
    def decorator(fn: Callable) -> Callable:
        spec = ToolSpec(
            name=name,
            description=description,
            category=category,
            parameters=parameters or {},
            permission_default=permission_default,
            handler=fn,
            team_id=team_id,
            agent_id=agent_id,
        )
        # Attach legacy marker (backward-compat with old loader path)
        fn._carole_tool_spec = spec  # type: ignore[attr-defined]

        # Populate module-level __carole_tools__ for fast-path discovery
        import sys
        calling_module = sys.modules.get(fn.__module__)
        if calling_module is not None:
            if not hasattr(calling_module, "__carole_tools__"):
                calling_module.__carole_tools__ = []
            calling_module.__carole_tools__.append(spec)

        return fn
    return decorator
