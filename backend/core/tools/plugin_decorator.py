"""
# backend/core/tools/plugin_decorator.py

Provides the @carole_tool decorator for writing drop-in plugin tools.

Usage:
    @carole_tool(
        name="sentiment_check",
        description="Analyze the sentiment of a block of text",
        category="custom",
        permission_default="safe",
        parameters={"text": {"type": "string", "required": True}},
    )
    async def sentiment_check(args: dict, team_id: str) -> str:
        text = args.get("text", "")
        return f"Positive sentiment detected in: {text[:50]}"
"""

from typing import Dict, Any
from core.tools.tool_registry import ToolSpec


def carole_tool(
    name: str,
    description: str,
    category: str = "custom",
    permission_default: str = "safe",
    parameters: Dict[str, Any] = None,
):
    """Decorator that stamps a ToolSpec onto the function so the plugin
    loader can pick it up automatically."""

    def decorator(fn):
        spec = ToolSpec(
            name=name,
            description=description,
            category=category,
            parameters=parameters or {},
            permission_default=permission_default,
            handler=fn,
        )
        fn._carole_tool_spec = spec
        return fn

    return decorator
