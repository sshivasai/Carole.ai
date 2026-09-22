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
from copy import deepcopy
from typing import Callable, Awaitable, Dict, List, Optional, Any, Set, Tuple

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
    input_schema: Optional[Dict[str, Any]] = None
    requires_instance_owner: bool = False


def tool_input_schema(spec: ToolSpec) -> dict:
    """Keep full MCP schemas, including definitions and nested required fields."""
    if spec.input_schema is not None:
        return deepcopy(spec.input_schema)
    properties, required = {}, []
    for name, info in spec.parameters.items():
        prop = deepcopy(info)
        if prop.pop("_required", prop.get("required") is True):
            required.append(name)
        if isinstance(prop.get("required"), bool):
            prop.pop("required")
        if not any(key in prop for key in ("type", "$ref", "anyOf", "oneOf", "allOf")):
            prop["type"] = "string"
        if prop.get("type") == "array":
            prop.setdefault("items", {})
        properties[name] = prop
    return {"type": "object", "properties": properties, "required": required}


class ToolRegistry:
    """Global, mutable tool registry.  Thread-safe enough for a single
    event-loop asyncio server (no concurrent writes from multiple threads)."""

    _tools: Dict[str, ToolSpec] = {}
    _schema_cache: Dict[Tuple, Any] = {}
    _plugin_tools: Dict[str, Set[str]] = {}

    # ---- core CRUD ----

    @classmethod
    def validate_spec(cls, spec: ToolSpec) -> None:
        """Validate ToolSpec structure, name format, permission default, and handler."""
        import re
        if not isinstance(spec, ToolSpec):
            raise TypeError(f"Expected ToolSpec instance, got {type(spec).__name__}")
        if not isinstance(spec.name, str) or not re.match(r'^[a-zA-Z_][a-zA-Z0-9_\-]*$', spec.name):
            raise ValueError(f"Invalid tool name: {getattr(spec, 'name', None)}")
        if not isinstance(spec.description, str) or not spec.description.strip():
            raise ValueError(f"Tool '{spec.name}' description must be a non-empty string")
        if not isinstance(spec.category, str) or not spec.category.strip():
            raise ValueError(f"Tool '{spec.name}' category must be a non-empty string")
        if spec.permission_default not in {"safe", "judge", "human"}:
            raise ValueError(
                f"Tool '{spec.name}' invalid permission_default: '{spec.permission_default}'. "
                "Must be 'safe', 'judge', or 'human'."
            )
        if not isinstance(spec.parameters, dict):
            raise ValueError(f"Tool '{spec.name}' parameters must be a dictionary schema")
        for p_name, p_info in spec.parameters.items():
            if not isinstance(p_name, str) or not isinstance(p_info, dict):
                raise ValueError(f"Tool '{spec.name}' parameter '{p_name}' must be a dict specification")
            # Accept both explicit 'type' and valid JSON Schema composition keywords
            # (anyOf, oneOf, allOf, $ref) which are common in MCP server schemas.
            has_type_decl = (
                "type" in p_info
                or "anyOf" in p_info
                or "oneOf" in p_info
                or "allOf" in p_info
                or "$ref" in p_info
            )
            if not has_type_decl:
                raise ValueError(f"Tool '{spec.name}' parameter '{p_name}' must declare a 'type', 'anyOf', 'oneOf', 'allOf', or '$ref'")
        if not callable(spec.handler):
            raise ValueError(f"Handler for '{spec.name}' is not callable")

    @classmethod
    def register(cls, spec: ToolSpec, force: bool = False) -> None:
        cls.validate_spec(spec)
        if spec.name in cls._tools and not force:
            raise ValueError(f"Tool '{spec.name}' already registered")
        cls._tools[spec.name] = spec
        cls._schema_cache.clear()

    @classmethod
    def register_batch(cls, specs: List[ToolSpec], force: bool = False) -> None:
        """Validate an entire batch of tools before mutating the registry."""
        for spec in specs:
            cls.validate_spec(spec)
            if spec.name in cls._tools and not force:
                raise ValueError(f"Tool '{spec.name}' already registered")
        for spec in specs:
            cls._tools[spec.name] = spec
        cls._schema_cache.clear()

    @classmethod
    def unregister(cls, name: str) -> bool:
        cls._schema_cache.clear()
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
            if spec.team_id is not None and str(spec.team_id) != str(team_id):
                continue
            if spec.agent_id is not None and str(spec.agent_id) != str(agent_id):
                continue

            # Keep description concise (first sentence/line)
            raw_desc = (spec.description or "").strip().split("\n")[0].strip()
            if len(raw_desc) > 180:
                raw_desc = raw_desc[:177] + "..."

            if spec.parameters:
                param_parts = []
                for k, v in spec.parameters.items():
                    param_type = v.get("type", "string")
                    required = v.get("_required", v.get("required") is True)
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
        """Returns an OpenAI-spec 'tools' array for native function calling (delegates to to_openai_tools)."""
        return cls.to_openai_tools(team_id=team_id, agent_id=agent_id)

    @classmethod
    def to_anthropic_tools(
        cls,
        team_id: str = None,
        agent_id: str = None,
        categories: Optional[Set[str]] = None,
        include_names: Optional[Set[str]] = None,
    ) -> List[dict]:
        """Convert ToolSpec registry to Anthropic native tool schema.

        Returns a list ready to pass as the ``tools`` parameter of the
        Anthropic Messages API. Optional ``categories`` and ``include_names``
        filter the tools for permission-aware selection and relevance-based loading.
        Tools are sorted alphabetically by name for deterministic prompt caching.
        """
        cache_key = (
            "anthropic",
            team_id,
            agent_id,
            tuple(sorted(categories)) if categories is not None else None,
            tuple(sorted(include_names)) if include_names is not None else None,
        )
        if cache_key in cls._schema_cache:
            return deepcopy(cls._schema_cache[cache_key])

        tools = []
        for spec in sorted(cls._tools.values(), key=lambda s: s.name):
            if spec.team_id is not None and str(spec.team_id) != str(team_id):
                continue
            if spec.agent_id is not None and str(spec.agent_id) != str(agent_id):
                continue
            if categories is not None and spec.category not in categories:
                continue
            if include_names is not None and spec.name not in include_names:
                continue

            description = spec.description or ""
            if spec.name == "browser_navigate":
                try:
                    from core.llm.config_manager import load_config
                    provider = load_config().get("browser_automation", {}).get("provider", "local")
                    if provider != "local":
                        description += f" (Anti-bot/CAPTCHA bypassing ENABLED via {provider.capitalize()})."
                except Exception:
                    pass

            tools.append({
                "name": spec.name,
                "description": description[:1024],
                "input_schema": tool_input_schema(spec),
            })
        cls._schema_cache[cache_key] = tools
        return deepcopy(tools)

    @classmethod
    def to_openai_tools(
        cls,
        team_id: str = None,
        agent_id: str = None,
        categories: Optional[Set[str]] = None,
        include_names: Optional[Set[str]] = None,
        strict: bool = False,
    ) -> List[dict]:
        """Convert ToolSpec registry to OpenAI function-calling schema.

        Wraps ``to_anthropic_tools()`` in the OpenAI ``{"type": "function", ...}``
        envelope so you can pass the result directly as the ``tools`` parameter of
        the OpenAI Chat Completions API.
        """
        cache_key = (
            "openai",
            team_id,
            agent_id,
            tuple(sorted(categories)) if categories is not None else None,
            tuple(sorted(include_names)) if include_names is not None else None,
            strict,
        )
        if cache_key in cls._schema_cache:
            return deepcopy(cls._schema_cache[cache_key])

        anthropic_tools = cls.to_anthropic_tools(
            team_id=team_id,
            agent_id=agent_id,
            categories=categories,
            include_names=include_names,
        )
        res = []
        for t in anthropic_tools:
            params = dict(t["input_schema"])
            fn_dict: Dict[str, Any] = {
                "name": t["name"],
                "description": t["description"],
            }
            if strict:
                fn_dict["strict"] = True
                params["additionalProperties"] = False
                params["required"] = list(params.get("properties", {}).keys())
            fn_dict["parameters"] = params
            res.append({
                "type": "function",
                "function": fn_dict,
            })
        cls._schema_cache[cache_key] = res
        return deepcopy(res)

    @classmethod
    def to_gemini_tools(
        cls,
        team_id: str = None,
        agent_id: str = None,
        categories: Optional[Set[str]] = None,
        include_names: Optional[Set[str]] = None,
    ) -> List[dict]:
        """Convert ToolSpec registry to Gemini FunctionDeclaration format."""
        cache_key = (
            "gemini",
            team_id,
            agent_id,
            tuple(sorted(categories)) if categories is not None else None,
            tuple(sorted(include_names)) if include_names is not None else None,
        )
        if cache_key in cls._schema_cache:
            return deepcopy(cls._schema_cache[cache_key])

        # Gemini uses uppercase type names: STRING, INTEGER, BOOLEAN, ARRAY, OBJECT
        _TYPE_MAP = {
            "string": "STRING",
            "str": "STRING",
            "integer": "INTEGER",
            "int": "INTEGER",
            "number": "NUMBER",
            "float": "NUMBER",
            "boolean": "BOOLEAN",
            "bool": "BOOLEAN",
            "array": "ARRAY",
            "list": "ARRAY",
            "object": "OBJECT",
            "dict": "OBJECT",
        }

        declarations = []
        for spec in sorted(cls._tools.values(), key=lambda s: s.name):
            if spec.team_id is not None and str(spec.team_id) != str(team_id):
                continue
            if spec.agent_id is not None and str(spec.agent_id) != str(agent_id):
                continue
            if categories is not None and spec.category not in categories:
                continue
            if include_names is not None and spec.name not in include_names:
                continue

            properties: dict = {}
            required: list = []
            for param_name, param_info in (spec.parameters or {}).items():
                if isinstance(param_info, dict):
                    def gemini_schema(schema):
                        out = deepcopy(schema)
                        out.pop("_required", None)
                        if isinstance(out.get("required"), bool):
                            out.pop("required")
                        raw_type = out.get("type", "string")
                        if isinstance(raw_type, list):
                            out["nullable"] = "null" in raw_type
                            raw_type = next((t for t in raw_type if t != "null"), "string")
                        out["type"] = _TYPE_MAP.get(str(raw_type).lower(), "STRING")
                        if "properties" in out:
                            out["properties"] = {k: gemini_schema(v) for k, v in out["properties"].items()}
                        if out["type"] == "ARRAY":
                            out["items"] = gemini_schema(out.get("items", {"type": "string"}))
                        return out
                    prop = gemini_schema(param_info)
                    properties[param_name] = prop
                    if param_info.get("_required", param_info.get("required") is True):
                        required.append(param_name)
                else:
                    properties[param_name] = {"type": "STRING", "description": str(param_info)}
                    required.append(param_name)

            decl: dict = {
                "name": spec.name,
                "description": (spec.description or "")[:1024],
                "parameters": {
                    "type": "OBJECT",
                    "properties": properties,
                },
            }
            if required:
                decl["parameters"]["required"] = required

            declarations.append(decl)

        result = [{"functionDeclarations": declarations}] if declarations else []
        cls._schema_cache[cache_key] = result
        return deepcopy(result)

    # ---- plugin loading ----

    @classmethod
    def load_plugin_directory(cls, directory: str) -> int:
        """Atomically replace each trusted plugin's registrations by provenance."""
        from pathlib import Path
        import hashlib
        root = Path(directory).resolve()
        if not root.is_dir():
            return 0
        paths = {str(p.resolve()) for p in root.glob("*.py") if not p.name.startswith("_") and not p.is_symlink()}
        for old_path in list(cls._plugin_tools):
            if Path(old_path).parent == root and old_path not in paths:
                for name in cls._plugin_tools.pop(old_path):
                    cls.unregister(name)
        loaded = 0
        for filepath in sorted(paths):
            module_name = "carole_plugin_" + hashlib.sha256(filepath.encode()).hexdigest()[:20]
            old_names = cls._plugin_tools.get(filepath, set())
            previous_module = sys.modules.get(module_name)
            try:
                mod_spec = importlib.util.spec_from_file_location(module_name, filepath)
                mod = importlib.util.module_from_spec(mod_spec)
                sys.modules[module_name] = mod
                # Compile source directly: same-size edits within one timestamp
                # tick must not silently reuse a stale .pyc.
                source = Path(filepath).read_text(encoding="utf-8")
                exec(compile(source, filepath, "exec"), mod.__dict__)
                specs = getattr(mod, "__carole_tools__", None)
                if specs is None:
                    specs = [getattr(value, "_carole_tool_spec") for value in vars(mod).values()
                             if hasattr(value, "_carole_tool_spec")]
                if not isinstance(specs, (list, tuple)):
                    raise ValueError("Plugin exports must be a list of ToolSpec")
                names = set()
                for spec in specs:
                    cls.validate_spec(spec)
                    spec.requires_instance_owner = True
                    if spec.name in names or (spec.name in cls._tools and spec.name not in old_names):
                        raise ValueError(f"Plugin cannot replace another source's tool: {spec.name}")
                    names.add(spec.name)
                replacement = {key: value for key, value in cls._tools.items() if key not in old_names}
                replacement.update({spec.name: spec for spec in specs})
                cls._tools = replacement
                cls._plugin_tools[filepath] = names
                cls._schema_cache.clear()
                loaded += len(specs)
            except Exception:
                if previous_module is None:
                    sys.modules.pop(module_name, None)
                else:
                    sys.modules[module_name] = previous_module
                logger.exception("Plugin reload rejected; previous tools retained: %s", filepath)
                raise
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
