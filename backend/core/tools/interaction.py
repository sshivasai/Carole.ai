"""
User interaction tools: ask questions, show messages, get confirmations
"""

from typing import Optional, List
from . import battlefield_tool


# In a real implementation, these would interface with the UI
# For now, they return structured data that the agent loop can handle


@battlefield_tool(
    name="ask_user",
    description="Ask the user a question and wait for response",
    category="interaction",
    parameters={
        "question": {"type": "string", "required": True, "description": "Question to ask"},
        "options": {"type": "array", "required": False, "description": "Multiple choice options"}
    }
)
def ask_user(question: str, options: Optional[List[str]] = None) -> str:
    """Ask user a question"""
    # In real implementation, this would pause execution and wait for user input
    # For now, return a placeholder

    result = [f"❓ Question for user: {question}"]

    if options:
        result.append("\nOptions:")
        for i, option in enumerate(options, 1):
            result.append(f"  {i}. {option}")

    result.append("\n[Waiting for user response...]")

    return "\n".join(result)


@battlefield_tool(
    name="request_confirmation",
    description="Request user confirmation before proceeding",
    category="interaction",
    parameters={
        "action": {"type": "string", "required": True, "description": "Action requiring confirmation"},
        "details": {"type": "string", "required": False, "description": "Additional details"}
    }
)
def request_confirmation(action: str, details: Optional[str] = None) -> str:
    """Request confirmation"""
    result = [f"⚠️  Confirmation required: {action}"]

    if details:
        result.append(f"\nDetails: {details}")

    result.append("\n[Waiting for user approval...]")

    return "\n".join(result)


@battlefield_tool(
    name="show_progress",
    description="Show progress update to user",
    category="interaction",
    parameters={
        "message": {"type": "string", "required": True, "description": "Progress message"},
        "percentage": {"type": "number", "required": False, "description": "Completion percentage (0-100)"}
    }
)
def show_progress(message: str, percentage: Optional[float] = None) -> str:
    """Show progress"""
    if percentage is not None:
        bar_length = 20
        filled = int(bar_length * percentage / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        return f"⏳ {message}\n[{bar}] {percentage:.0f}%"
    else:
        return f"⏳ {message}"


@battlefield_tool(
    name="notify_user",
    description="Send a notification to the user",
    category="interaction",
    parameters={
        "message": {"type": "string", "required": True, "description": "Notification message"},
        "level": {"type": "string", "required": False, "description": "Level: info, success, warning, error"}
    }
)
def notify_user(message: str, level: str = "info") -> str:
    """Send notification"""
    icons = {
        'info': 'ℹ️',
        'success': '✓',
        'warning': '⚠️',
        'error': '✗'
    }

    icon = icons.get(level, 'ℹ️')
    return f"{icon} {message}"


@battlefield_tool(
    name="show_options_menu",
    description="Display a menu of options for user to choose from",
    category="interaction",
    parameters={
        "title": {"type": "string", "required": True, "description": "Menu title"},
        "options": {"type": "array", "required": True, "description": "List of options"}
    }
)
def show_options_menu(title: str, options: List[str]) -> str:
    """Show options menu"""
    result = [f"📋 {title}\n"]

    for i, option in enumerate(options, 1):
        result.append(f"  {i}. {option}")

    result.append("\n[Waiting for selection...]")

    return "\n".join(result)
