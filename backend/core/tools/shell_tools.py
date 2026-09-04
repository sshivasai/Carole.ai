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
import signal
import asyncio
import subprocess
import threading
import logging
import re
from pathlib import Path
from typing import Optional

from core.tools.context import ToolExecutionContext

logger = logging.getLogger("carole.shell_tools")


class ProcessRegistry:
    """
    Centralized registry of all processes launched by agents and users.
    Enables PID tracking, status inspection, and UI-driven aborts.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._processes: dict = {}

    def register(self, proc: subprocess.Popen, command: str, team_id: str, cwd: str, background: bool = False):
        with self._lock:
            import datetime
            self._processes[proc.pid] = {
                "pid": proc.pid,
                "command": command,
                "team_id": team_id,
                "cwd": cwd,
                "background": background,
                "status": "running",
                "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "proc": proc,
                "returncode": None,
            }

    def update_status(self, pid: int, status: str, returncode: Optional[int] = None):
        with self._lock:
            if pid in self._processes:
                self._processes[pid]["status"] = status
                self._processes[pid]["returncode"] = returncode

    def list_processes(self, team_id: Optional[str] = None) -> list:
        with self._lock:
            procs = []
            for p_info in self._processes.values():
                if team_id and str(p_info.get("team_id")) != str(team_id):
                    continue
                procs.append({
                    "pid": p_info["pid"],
                    "command": p_info["command"],
                    "team_id": p_info["team_id"],
                    "cwd": p_info["cwd"],
                    "background": p_info["background"],
                    "status": p_info["status"],
                    "started_at": p_info["started_at"],
                    "returncode": p_info["returncode"],
                })
            return procs

    def kill_process(self, pid: int) -> bool:
        with self._lock:
            info = self._processes.get(pid)
            if not info:
                return False
            proc = info.get("proc")
            if not proc or proc.poll() is not None:
                info["status"] = "terminated"
                return False
            
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
                    proc.kill()
                else:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except Exception:
                        proc.kill()
                info["status"] = "aborted"
                info["returncode"] = -9
                return True
            except Exception as e:
                logger.warning("Failed to kill process %s: %s", pid, e)
                return False


process_registry = ProcessRegistry()


class ShellTools:
    def __init__(self, workspace_root: str = None):
        if not workspace_root:
            # Resolved relative to this file's position in /backend/core/tools/
            workspace_root = os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[3]))
        self.workspace_root = Path(workspace_root).resolve()

    @staticmethod
    def _validate_strict_command_policy(command: str) -> Optional[str]:
        """
        Enforces Strict Tool Exclusivity:
        Intercepts raw shell commands attempting to read, write, edit, or search files
        when dedicated structured tools exist.
        """
        cmd_clean = command.strip()

        # 1. Reading files via shell escapes (cat, head, tail, Get-Content, type)
        m_read = re.match(r'^\s*(?:cat|head|tail|Get-Content|gc|type)\s+([^\s|>;&]+)\s*$', cmd_clean, re.IGNORECASE)
        if m_read:
            target_path = m_read.group(1).strip('\'"')
            return (
                f"Strict Tool Policy Violation: Do NOT use shell commands like 'cat/head/tail/Get-Content' to read files.\n"
                f"Action Required: Use the dedicated 'read_file' tool: read_file(relative_path=\"{target_path}\")"
            )

        # 2. In-place file editing via sed / awk
        if re.search(r'^\s*(?:sed\s+-i|awk\s+.*-i)\b', cmd_clean, re.IGNORECASE):
            return (
                "Strict Tool Policy Violation: Do NOT use 'sed -i' or 'awk' to edit files.\n"
                "Action Required: Use the dedicated 'edit_file' tool with exact character matching."
            )

        # 3. File creation via heredocs or echo redirection
        if re.search(r'^\s*cat\s*<<\s*[\'"]?EOF[\'"]?\s*>', cmd_clean, re.IGNORECASE) or \
           re.search(r'^\s*(?:Set-Content|Out-File)\s+', cmd_clean, re.IGNORECASE):
            return (
                "Strict Tool Policy Violation: Do NOT use shell heredocs (cat << EOF) or Set-Content to write files.\n"
                "Action Required: Use the dedicated 'write_file' tool: write_file(relative_path=\"...\", content=\"...\")"
            )

        return None

    async def execute_command(
        self,
        command: str,
        team_id: str,
        timeout: float = 900.0,
        context: Optional[ToolExecutionContext] = None,
        cwd: Optional[str] = None,
        background: bool = False,
    ) -> str:
        """
        Executes a shell command inside the workspace directory asynchronously.
        Streams standard output and standard error line-by-line to the EventBus.
        Respects CancellationToken for aborts. Works robustly across all platforms.
        Supports background=True for long-running daemon processes (e.g. dev servers, pip install).
        """
        # Strict tool exclusivity check
        policy_violation = self._validate_strict_command_policy(command)
        if policy_violation:
            logger.warning("[Shell] Intercepted non-exclusive command: %s", command)
            return policy_violation
        workdir = cwd or str(self.workspace_root)
        try:
            sanitized_cmd = re.sub(r'(Bearer\s+|api[_-]?key[=:\s]+|token[=:\s]+|password[=:\s]+)([\w\-.~]+)', r'\1***REDACTED***', command, flags=re.IGNORECASE)
            sanitized_cmd = re.sub(r'sk-[a-zA-Z0-9_\-]{16,}', 'sk-***REDACTED***', sanitized_cmd)
            logger.info("[Shell] Executing in %s: '%s' (Timeout: %ss, Background: %s)", workdir, sanitized_cmd, timeout, background)
        except Exception:
            sanitized_cmd = command

        loop = asyncio.get_running_loop()
        topic = f"team:{team_id}"

        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["preexec_fn"] = os.setpgrp

        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                cwd=workdir,
                **kwargs
            )
        except Exception as e:
            return f"✗ Subprocess Launch Error: {str(e)}"

        pid = proc.pid
        process_registry.register(proc, sanitized_cmd, team_id, workdir, background=background)

        # Broadcast process start event to EventBus
        try:
            from core.chat.event_bus import event_bus
            await event_bus.publish(topic, {
                "type": "process_started",
                "pid": pid,
                "command": sanitized_cmd,
                "background": background,
            })
        except Exception:
            pass

        def kill_proc_tree(p):
            process_registry.kill_process(p.pid)

        stdout_chunks = []
        stderr_chunks = []

        def read_stream(stream, is_stderr: bool):
            for line in iter(stream.readline, ''):
                if not line:
                    break
                if context and context.cancellation_token and context.cancellation_token.is_cancelled:
                    kill_proc_tree(proc)
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

                # Broadcast to live eventbus for frontend terminal with PID
                try:
                    from core.chat.event_bus import event_bus
                    asyncio.run_coroutine_threadsafe(
                        event_bus.publish(topic, {
                            "type": "shell_output",
                            "pid": pid,
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

        # If running in background mode (e.g. dev server, background pip install)
        if background:
            def _watch_background_process():
                proc.wait()
                process_registry.update_status(pid, "completed" if proc.returncode == 0 else "failed", proc.returncode)
                try:
                    from core.chat.event_bus import event_bus
                    asyncio.run_coroutine_threadsafe(
                        event_bus.publish(topic, {
                            "type": "process_completed",
                            "pid": pid,
                            "command": sanitized_cmd,
                            "returncode": proc.returncode,
                            "status": "completed" if proc.returncode == 0 else "failed",
                        }),
                        loop
                    )
                except Exception:
                    pass

            threading.Thread(target=_watch_background_process, daemon=True).start()

            return (
                f"✓ Command launched in background with PID {pid}.\n"
                f"Command: '{sanitized_cmd}'\n"
                f"Logs are streaming to the terminal widget. You can monitor or terminate this PID from the UI or via terminal tools."
            )

        # Foreground mode: wait for completion synchronously
        def _execute_wait():
            timed_out = False
            cancelled = False
            interval = 0.2
            elapsed = 0.0

            while proc.poll() is None:
                if context and context.cancellation_token and context.cancellation_token.is_cancelled:
                    cancelled = True
                    kill_proc_tree(proc)
                    break

                if elapsed >= timeout:
                    timed_out = True
                    kill_proc_tree(proc)
                    break

                import time
                time.sleep(interval)
                elapsed += interval

            t_out.join(timeout=2.0)
            t_err.join(timeout=2.0)

            status = "cancelled" if cancelled else ("timed_out" if timed_out else ("completed" if proc.returncode == 0 else "failed"))
            process_registry.update_status(pid, status, proc.returncode)

            return proc.returncode, "".join(stdout_chunks), "".join(stderr_chunks), timed_out, cancelled

        try:
            returncode, full_stdout, full_stderr, timed_out, cancelled = await asyncio.to_thread(_execute_wait)
        except Exception as e:
            return f"✗ Subprocess Execution Error: {str(e)}"

        if cancelled:
            return f"✗ Command Cancelled: Process (PID: {pid}) was aborted by user request."

        if timed_out:
            return f"✗ Subprocess Error: Command (PID: {pid}) exceeded time constraint of {timeout} seconds and was killed."

        # Truncate to prevent context window overflow from verbose commands while preserving stack traces at the tail
        def _truncate_output(text: str, max_chars: int = 8000) -> str:
            if not text or len(text) <= max_chars:
                return text
            head_size = 1500
            tail_size = max_chars - head_size
            omitted = len(text) - (head_size + tail_size)
            return (
                f"{text[:head_size]}\n\n"
                f"... [Output truncated — {omitted} characters omitted. Use read_file to see full output if saved to a file] ...\n\n"
                f"{text[-tail_size:]}"
            )

        full_stdout = _truncate_output(full_stdout)
        full_stderr = _truncate_output(full_stderr)

        if returncode != 0:
            return (
                f"✗ Command failed with exit code {returncode} (PID: {pid}).\n"
                f"--- Standard Error ---\n{full_stderr}\n"
                f"--- Standard Output ---\n{full_stdout}"
            )

        return full_stdout or full_stderr or f"Command executed successfully with exit code 0 (PID: {pid})."


# Singleton shell tools instance
shell_tools = ShellTools()
