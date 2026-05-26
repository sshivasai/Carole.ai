"""
# backend/core/tools/shell_tools.py

This module contains execution environments for the agents.

Responsibilities:
1. Provide `BashTool`, `PowerShellTool`, and `REPLTool`.
2. Allow agents to execute tests, run compilation steps, and start servers.
3. Capture `stdout` and `stderr` and stream it back via the EventBus for live viewing.
"""

class ShellTools:
    # TODO: Implement secure subprocess execution
    pass
