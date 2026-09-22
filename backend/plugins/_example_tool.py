"""
Example plugin tool — demonstrates how to add custom tools to Carole.ai.

Drop any .py file in this /plugins/ directory and it will be auto-loaded
on server startup.  Use the @carole_tool decorator to register.
"""

from core.tools.plugin_decorator import carole_tool


@carole_tool(
    name="count_words",
    description="Count the number of words in a block of text",
    category="custom",
    permission_default="safe",
    parameters={"text": {"type": "string", "required": True}},
)
async def count_words(args: dict, team_id: str) -> str:
    text = args.get("text", "")
    count = len(text.split())
    return f"Word count: {count}"
