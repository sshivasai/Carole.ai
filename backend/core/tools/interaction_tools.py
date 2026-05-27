"""
# backend/core/tools/interaction_tools.py

This module contains tools for direct Agent-to-Human or Agent-to-System interaction.

Responsibilities:
1. Provide `AskUserQuestionTool` for when an agent is genuinely stuck and requires human clarification before proceeding.
2. Provide `PermissionRequestTool` (optional) if an agent wants to proactively ask for temporary elevation of privileges.
3. Provide `SleepTool` to intentionally pause execution while waiting for external async systems to resolve.
4. (Handled by Engine) Standard tool permission requests (Safe vs Human-Only) are intercepted automatically by the ToolExecutor and piped to the EventBus, rather than requiring an explicit tool call.
"""

class InteractionTools:
    # TODO: Implement human interaction and sleep utilities
    pass
