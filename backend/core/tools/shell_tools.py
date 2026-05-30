"""
# backend/core/tools/shell_tools.py

This module contains execution environments for the agents.

Responsibilities:
1. Provide dynamic subprocess command execution (Bash/PowerShell).
2. Allow agents to execute tests, run compilation steps, and start servers.
3. Capture `stdout` and `stderr` asynchronously.
4. Stream terminal chunks in real-time via the EventBus for live-view terminal widgets.
5. Enforce process execution timeouts to prevent hanging resources.
"""

import os
import asyncio
from pathlib import Path
from typing import Dict, Any

class ShellTools:
    def __init__(self, workspace_root: str = None):
        if not workspace_root:
            # Resolved relative to this file's position in /backend/core/tools/
            workspace_root = os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[3]))
        self.workspace_root = Path(workspace_root).resolve()

    async def execute_command(self, command: str, team_id: str, timeout: float = 60.0) -> str:
        """
        Executes a shell command inside the workspace directory asynchronously.
        Streams standard output and standard error line-by-line to the EventBus.
        """
        print(f"🐚 [Shell] Executing: '{command}' (Timeout: {timeout}s)")
        
        # Spawn subprocess safely inside the defined workspace directory
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.workspace_root)
        )

        topic = f"team:{team_id}"
        stdout_chunks = []
        stderr_chunks = []

        async def read_stream(stream, is_stderr: bool):
            """Concurrently reads and streams stdout/stderr lines."""
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded_line = line.decode("utf-8", errors="replace")
                
                if is_stderr:
                    stderr_chunks.append(decoded_line)
                else:
                    stdout_chunks.append(decoded_line)

                # Dynamically broadcast each output line to the WebSocket event bus!
                # Allows the frontend to render a scrolling, live terminal interface.
                from core.chat.event_bus import event_bus
                await event_bus.publish(topic, {
                    "type": "shell_output",
                    "stream": "stderr" if is_stderr else "stdout",
                    "text": decoded_line
                })

        try:
            # Read stdout and stderr concurrently with a timeout constraint
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(process.stdout, False),
                    read_stream(process.stderr, True)
                ),
                timeout=timeout
            )
            # Wait for process exit status
            await process.wait()
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            return f"✗ Subprocess Error: Command exceeded time constraint of {timeout} seconds and was killed."

        full_stdout = "".join(stdout_chunks)
        full_stderr = "".join(stderr_chunks)

        if process.returncode != 0:
            return (
                f"✗ Command failed with exit code {process.returncode}.\n"
                f"--- Standard Error ---\n{full_stderr}\n"
                f"--- Standard Output ---\n{full_stdout}"
            )
        
        return full_stdout

# Singleton shell tools instance
shell_tools = ShellTools()
