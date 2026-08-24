"""
# backend/core/tools/shell_tools.py

This module contains execution environments for the agents.

Responsibilities:
1. Provide dynamic subprocess command execution (Bash/PowerShell/CMD).
2. Allow agents to execute tests, run compilation steps, and start servers.
3. Capture `stdout` and `stderr` asynchronously with cross-platform event loop compatibility (Windows/Linux/macOS).
4. Stream terminal chunks in real-time via the EventBus for live-view terminal widgets.
5. Enforce process execution timeouts to prevent hanging resources.
"""

import os
import sys
import asyncio
import subprocess
import threading
import logging
from pathlib import Path
from typing import Optional

from core.tools.context import ToolExecutionContext

logger = logging.getLogger("carole.shell_tools")


class ShellTools:
    def __init__(self, workspace_root: str = None):
        if not workspace_root:
            # Resolved relative to this file's position in /backend/core/tools/
            workspace_root = os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[3]))
        self.workspace_root = Path(workspace_root).resolve()

    async def execute_command(
        self,
        command: str,
        team_id: str,
        timeout: float = 60.0,
        context: Optional[ToolExecutionContext] = None,
        cwd: Optional[str] = None
    ) -> str:
        """
        Executes a shell command inside the workspace directory asynchronously.
        Streams standard output and standard error line-by-line to the EventBus.
        Respects CancellationToken for aborts. Works robustly across all platforms.
        """
        workdir = cwd or str(self.workspace_root)
        try:
            logger.info("[Shell] Executing in %s: '%s' (Timeout: %ss)", workdir, command, timeout)
        except Exception:
            pass

        loop = asyncio.get_running_loop()
        topic = f"team:{team_id}"

        def _execute_sync():
            # Use subprocess.Popen with pipes for cross-platform compatibility (Proactor/Selector agnostic)
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                cwd=workdir
            )

            stdout_chunks = []
            stderr_chunks = []

            def read_stream(stream, is_stderr: bool):
                for line in iter(stream.readline, ''):
                    if not line:
                        break
                    if context and context.cancellation_token and context.cancellation_token.is_cancelled:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        break

                    if is_stderr:
                        stderr_chunks.append(line)
                    else:
                        stdout_chunks.append(line)

                    # Emit to progress
                    if context and context.emit_progress:
                        try:
                            asyncio.run_coroutine_threadsafe(
                                context.emit_progress(f"[{'stderr' if is_stderr else 'stdout'}] {line.strip()}"),
                                loop
                            )
                        except Exception:
                            pass

                    # Broadcast to live eventbus for frontend terminal
                    try:
                        from core.chat.event_bus import event_bus
                        asyncio.run_coroutine_threadsafe(
                            event_bus.publish(topic, {
                                "type": "shell_output",
                                "stream": "stderr" if is_stderr else "stdout",
                                "text": line
                            }),
                            loop
                        )
                    except Exception:
                        pass
                stream.close()

            t_out = threading.Thread(target=read_stream, args=(proc.stdout, False), daemon=True)
            t_err = threading.Thread(target=read_stream, args=(proc.stderr, True), daemon=True)
            t_out.start()
            t_err.start()

            # Poll for completion with timeout and cancellation check
            timed_out = False
            cancelled = False
            interval = 0.2
            elapsed = 0.0

            while proc.poll() is None:
                if context and context.cancellation_token and context.cancellation_token.is_cancelled:
                    cancelled = True
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    break

                if elapsed >= timeout:
                    timed_out = True
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    break

                import time
                time.sleep(interval)
                elapsed += interval

            t_out.join(timeout=2.0)
            t_err.join(timeout=2.0)

            return proc.returncode, "".join(stdout_chunks), "".join(stderr_chunks), timed_out, cancelled

        try:
            returncode, full_stdout, full_stderr, timed_out, cancelled = await asyncio.to_thread(_execute_sync)
        except Exception as e:
            return f"✗ Subprocess Execution Error: {str(e)}"

        if cancelled:
            return "✗ Command Cancelled: Process was aborted by user request."

        if timed_out:
            return f"✗ Subprocess Error: Command exceeded time constraint of {timeout} seconds and was killed."

        # Truncate to prevent context window overflow from verbose commands
        MAX_SHELL_OUTPUT = 8000
        if len(full_stdout) > MAX_SHELL_OUTPUT:
            full_stdout = full_stdout[:MAX_SHELL_OUTPUT] + f"\n... [Output truncated — {len(full_stdout)} total chars. Use read_file to see full output if saved to a file.]"
        if len(full_stderr) > MAX_SHELL_OUTPUT:
            full_stderr = full_stderr[:MAX_SHELL_OUTPUT] + f"\n... [Stderr truncated — {len(full_stderr)} total chars]"

        if returncode != 0:
            return (
                f"✗ Command failed with exit code {returncode}.\n"
                f"--- Standard Error ---\n{full_stderr}\n"
                f"--- Standard Output ---\n{full_stdout}"
            )

        return full_stdout or full_stderr or "Command executed successfully (no output)."


# Singleton shell tools instance
shell_tools = ShellTools()
