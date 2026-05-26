"""
Battlefield Tool System
A lightweight, decorator-based tool registry for AI agents
"""

from typing import Callable, Dict, Any, List, Optional
from functools import wraps
import inspect

__all__ = ['battlefield_tool', 'ToolRegistry', 'Tool']


class Tool:
    """Represents a single tool with metadata"""

    def __init__(
        self,
        name: str,
        func: Callable,
        description: str,
        parameters: Dict[str, Any],
        category: str = "general",
        requires_confirmation: bool = False
    ):
        self.name = name
        self.func = func
        self.description = description
        self.parameters = parameters
        self.category = category
        self.requires_confirmation = requires_confirmation

    async def execute(self, **kwargs) -> Any:
        """Execute the tool with given arguments"""
        if inspect.iscoroutinefunction(self.func):
            return await self.func(**kwargs)
        return self.func(**kwargs)

    def to_schema(self) -> Dict[str, Any]:
        """Convert tool to LLM-friendly schema"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "category": self.category,
            "requires_confirmation": self.requires_confirmation
        }


class ToolRegistry:
    """Global registry for all tools"""

    _tools: Dict[str, Tool] = {}

    @classmethod
    def register(cls, tool: Tool):
        """Register a tool"""
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> Optional[Tool]:
        """Get a tool by name"""
        return cls._tools.get(name)

    @classmethod
    def list_all(cls) -> List[Tool]:
        """List all registered tools"""
        return list(cls._tools.values())

    @classmethod
    def get_by_category(cls, category: str) -> List[Tool]:
        """Get tools by category"""
        return [t for t in cls._tools.values() if t.category == category]

    @classmethod
    def to_llm_prompt(cls) -> str:
        """Generate a prompt describing all available tools"""
        if not cls._tools:
            return "No tools available."

        prompt = "Available tools:\n\n"

        categories = {}
        for tool in cls._tools.values():
            if tool.category not in categories:
                categories[tool.category] = []
            categories[tool.category].append(tool)

        for category, tools in sorted(categories.items()):
            prompt += f"## {category.upper()}\n\n"
            for tool in tools:
                prompt += f"**{tool.name}**\n"
                prompt += f"{tool.description}\n"
                prompt += f"Parameters: {tool.parameters}\n"
                if tool.requires_confirmation:
                    prompt += "⚠️ Requires user confirmation\n"
                prompt += "\n"

        return prompt


def battlefield_tool(
    name: str = None,
    description: str = "",
    category: str = "general",
    requires_confirmation: bool = False,
    parameters: Dict[str, Any] = None
):
    """
    Decorator to register a function as a battlefield tool

    Usage:
        @battlefield_tool(
            name="read_file",
            description="Read contents of a file",
            category="filesystem",
            parameters={"path": {"type": "string", "required": True}}
        )
        def read_file(path: str) -> str:
            with open(path, 'r') as f:
                return f.read()
    """
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__

        # Auto-generate parameters from function signature if not provided
        if parameters is None:
            sig = inspect.signature(func)
            auto_params = {}
            for param_name, param in sig.parameters.items():
                if param_name != 'self':
                    auto_params[param_name] = {
                        "type": param.annotation.__name__ if param.annotation != inspect.Parameter.empty else "any",
                        "required": param.default == inspect.Parameter.empty
                    }
            tool_params = auto_params
        else:
            tool_params = parameters

        tool = Tool(
            name=tool_name,
            func=func,
            description=description or func.__doc__ or "No description provided",
            parameters=tool_params,
            category=category,
            requires_confirmation=requires_confirmation
        )

        ToolRegistry.register(tool)

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator
