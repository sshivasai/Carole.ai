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
from typing import Optional

from core.tools.context import ToolExecutionContext

class ShellTools:
    def __init__(self, workspace_root: str = None):
        if not workspace_root:
            # Resolved relative to this file's position in /backend/core/tools/
            workspace_root = os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[3]))
        self.workspace_root = Path(workspace_root).resolve()

    async def execute_command(self, command: str, team_id: str, timeout: float = 60.0, context: Optional[ToolExecutionContext] = None, cwd: Optional[str] = None) -> str:
        """
        Executes a shell command inside the workspace directory asynchronously.
        Streams standard output and standard error line-by-line to the EventBus.
        Respects CancellationToken for aborts.

        `cwd` scopes the command to a specific directory (the agent's project
        workspace when provided by the executor). When omitted, falls back to
        the shared workspace root. Note: the OS shell can still escape the cwd
        via absolute paths / `..`, so this is a *default-context* sandbox, not
        a hard jail; destructive system commands are still gated by the Judge.
        """
        workdir = cwd or str(self.workspace_root)
        print(f"🐚 [Shell] Executing in {workdir}: '{command}' (Timeout: {timeout}s)")

        # Spawn subprocess safely inside the defined workspace directory
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir
        )

        topic = f"team:{team_id}"
        stdout_chunks = []
        stderr_chunks = []

        async def read_stream(stream, is_stderr: bool):
            """Concurrently reads and streams stdout/stderr lines."""
            while True:
                if context and context.cancellation_token and context.cancellation_token.is_cancelled:
                    break
                line = await stream.readline()
                if not line:
                    break
                decoded_line = line.decode("utf-8", errors="replace")
                
                if is_stderr:
                    stderr_chunks.append(decoded_line)
                else:
                    stdout_chunks.append(decoded_line)

                # Broadcast to progress stream if context provides it
                if context and context.emit_progress:
                    await context.emit_progress(f"[{'stderr' if is_stderr else 'stdout'}] {decoded_line.strip()}")

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
            monitor_task = asyncio.gather(
                read_stream(process.stdout, False),
                read_stream(process.stderr, True)
            )

            async def cancel_watcher():
                """Polls the cancellation token to kill process early."""
                if not context or not context.cancellation_token:
                    return
                while not monitor_task.done():
                    if context.cancellation_token.is_cancelled:
                        try:
                            process.kill()
                        except Exception:
                            pass
                        break
                    await asyncio.sleep(0.5)

            watcher_task = asyncio.create_task(cancel_watcher())

            await asyncio.wait_for(monitor_task, timeout=timeout)
            
            if not watcher_task.done():
                watcher_task.cancel()

            # Wait for process exit status
            await process.wait()
            
            if context and context.cancellation_token and context.cancellation_token.is_cancelled:
                return "✗ Command Cancelled: Process was aborted by user request."
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            # Reap the killed process to avoid zombie/defunct accumulation.
            try:
                await process.wait()
            except Exception:
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
