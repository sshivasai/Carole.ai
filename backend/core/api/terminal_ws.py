from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import asyncio
import subprocess
import threading
import sys
import os
import json
import logging
import shutil
from typing import Dict, Any, Optional

try:
    import winpty
    HAS_WINPTY = True
except ImportError:
    HAS_WINPTY = False

from core.tools.file_tools import file_tools

router = APIRouter(prefix="/api/terminal", tags=["terminal"])
logger = logging.getLogger(__name__)

def find_windows_bash() -> Optional[str]:
    """Helper to locate Git Bash on Windows, skipping WSL wrappers."""
    # 1. Check standard installation folders first (most reliable)
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    local_app_data = os.environ.get("LocalAppData", "")
    
    standard_paths = [
        os.path.join(program_files, "Git", "bin", "bash.exe"),
        os.path.join(program_files, "Git", "usr", "bin", "bash.exe"),
        os.path.join(program_files_x86, "Git", "bin", "bash.exe"),
        os.path.join(program_files_x86, "Git", "usr", "bin", "bash.exe"),
        os.path.join(local_app_data, "Programs", "Git", "bin", "bash.exe"),
    ]
    for p in standard_paths:
        if os.path.exists(p):
            return p
            
    # 2. Check PATH but filter out C:\Windows\System32\bash.exe (WSL launcher)
    bash_path = shutil.which("bash")
    if bash_path:
        lower_path = bash_path.lower()
        if "system32" not in lower_path and "syswow64" not in lower_path:
            return bash_path

    # 3. Check relative to git.exe location in PATH
    git_path = shutil.which("git")
    if git_path:
        git_dir = os.path.dirname(git_path)
        parent_git = os.path.dirname(git_dir)
        possible_paths = [
            os.path.join(parent_git, "bin", "bash.exe"),
            os.path.join(parent_git, "usr", "bin", "bash.exe"),
        ]
        for p in possible_paths:
            if os.path.exists(p):
                return p
    return None

def discover_windows_shell() -> str:
    """Helper to auto-discover the best available shell on Windows."""
    bash = find_windows_bash()
    if bash:
        return bash
    if shutil.which("powershell.exe"):
        return "powershell.exe"
    return "cmd.exe"

from collections import deque
import time

class TerminalSession:
    def __init__(self, session_id: str, session_type: str, process: Any, cwd: str, master_fd: Optional[int] = None, project_id: Optional[str] = None):
        self.session_id = session_id
        self.session_type = session_type
        self.process = process
        self.cwd = cwd
        self.project_id = project_id
        self.master_fd = master_fd
        self.scrollback: deque[str] = deque(maxlen=2000)
        self.connected_sockets: list[WebSocket] = []
        self.created_at = time.time()
        self.last_activity = time.time()
        self.cleanup_task: Optional[asyncio.Task] = None

    def append_output(self, data: str):
        self.scrollback.append(data)
        self.last_activity = time.time()

    def get_full_scrollback(self) -> str:
        return "".join(self.scrollback)

    def is_alive(self) -> bool:
        if self.session_type == "winpty":
            try:
                return self.process.isalive()
            except Exception:
                return False
        elif hasattr(self.process, "poll"):
            return self.process.poll() is None
        return True


class TerminalSessionManager:
    def __init__(self):
        self.active_sessions: Dict[str, TerminalSession] = {}

    def is_session_alive(self, session: TerminalSession) -> bool:
        return session.is_alive()

    async def _graceful_cleanup(self, session_id: str, delay: int = 600):
        try:
            await asyncio.sleep(delay)
            session = self.active_sessions.get(session_id)
            if session and len(session.connected_sockets) == 0:
                logger.info("Terminal session %s expired after %ds of inactivity. Terminating.", session_id, delay)
                self.terminate_session(session_id)
        except asyncio.CancelledError:
            pass

    def terminate_session(self, session_id: str):
        session = self.active_sessions.pop(session_id, None)
        if not session:
            return

        if session.cleanup_task and not session.cleanup_task.done():
            session.cleanup_task.cancel()

        session_type = session.session_type
        process = session.process

        if session_type == "unix_pty" and session.master_fd is not None:
            try:
                os.close(session.master_fd)
            except Exception:
                pass

        if process:
            try:
                if sys.platform == "win32":
                    pid = getattr(process, "pid", None)
                    if pid:
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
                else:
                    import signal
                    pid = getattr(process, "pid", None)
                    if pid:
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
            except Exception:
                try:
                    if hasattr(process, "terminate"):
                        process.terminate()
                    elif hasattr(process, "close"):
                        process.close()
                except Exception:
                    pass

    def disconnect(self, session_id: str):
        """Deprecated alias for terminate_session for compatibility."""
        self.terminate_session(session_id)

    async def connect(self, websocket: WebSocket, session_id: str, project_id: Optional[str] = None, shell: str = "default"):
        existing = self.active_sessions.get(session_id)
        if existing is not None and existing.project_id != project_id:
            await websocket.close(code=4003)
            return
        await websocket.accept()

        # Check for existing persistent session reattachment
        if session_id in self.active_sessions and self.is_session_alive(self.active_sessions[session_id]):
            session = self.active_sessions[session_id]
            logger.info("Reattaching WebSocket to persistent terminal session %s", session_id)
            if session.cleanup_task and not session.cleanup_task.done():
                session.cleanup_task.cancel()
            session.connected_sockets.append(websocket)

            # Replay scrollback buffer
            scrollback = session.get_full_scrollback()
            if scrollback:
                try:
                    await websocket.send_text(scrollback)
                except Exception as e:
                    logger.warning("Failed to replay scrollback: %s", e)

            # Enter message loop for existing session
            await self._run_input_loop(websocket, session)
            return

        # Get the working directory for this project
        cwd = await file_tools.get_workspace_root(project_id)
        if not cwd.exists():
            cwd.mkdir(parents=True, exist_ok=True)

        # Determine shell command
        shell_cmd = "cmd.exe"
        if sys.platform == "win32":
            if shell == "bash":
                shell_cmd = find_windows_bash() or "cmd.exe"
            elif shell == "powershell":
                shell_cmd = "powershell.exe"
            elif shell == "cmd":
                shell_cmd = "cmd.exe"
            else:  # default
                shell_cmd = discover_windows_shell()
        else:
            if shell == "powershell":
                shell_cmd = shutil.which("pwsh") or os.environ.get("SHELL", "/bin/bash")
            elif shell == "cmd":
                shell_cmd = os.environ.get("SHELL", "/bin/bash")
            elif shell == "bash":
                shell_cmd = "/bin/bash"
            else:
                shell_cmd = os.environ.get("SHELL", "/bin/bash")

        loop = asyncio.get_running_loop()

        try:
            if sys.platform == "win32" and HAS_WINPTY:
                process = winpty.PTY(80, 24)
                process.spawn(shell_cmd, cwd=str(cwd))
                session = TerminalSession(session_id, "winpty", process, str(cwd), project_id=project_id)
                session.connected_sockets.append(websocket)
                self.active_sessions[session_id] = session

                def read_output_winpty():
                    try:
                        while session_id in self.active_sessions and process.isalive():
                            data = process.read(blocking=True)
                            if not data:
                                break
                            session.append_output(data)
                            for ws in list(session.connected_sockets):
                                try:
                                    future = asyncio.run_coroutine_threadsafe(ws.send_text(data), loop)
                                    future.result(timeout=5.0)
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.debug("Winpty reader exiting: %s", e)

                thread = threading.Thread(target=read_output_winpty, daemon=True)
                thread.start()
                await self._run_input_loop(websocket, session)

            elif sys.platform != "win32":
                import pty
                import termios
                import fcntl
                import struct

                master_fd, slave_fd = pty.openpty()
                process = subprocess.Popen(
                    [shell_cmd],
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    cwd=str(cwd),
                    preexec_fn=os.setsid,
                    close_fds=True
                )
                os.close(slave_fd)

                session = TerminalSession(session_id, "unix_pty", process, str(cwd), master_fd=master_fd, project_id=project_id)
                session.connected_sockets.append(websocket)
                self.active_sessions[session_id] = session

                def read_output_pty():
                    try:
                        while session_id in self.active_sessions:
                            data = os.read(master_fd, 1024)
                            if not data:
                                break
                            text = data.decode("utf-8", errors="replace")
                            session.append_output(text)
                            for ws in list(session.connected_sockets):
                                try:
                                    future = asyncio.run_coroutine_threadsafe(ws.send_text(text), loop)
                                    future.result(timeout=5.0)
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.debug("Unix PTY reader exiting: %s", e)

                thread = threading.Thread(target=read_output_pty, daemon=True)
                thread.start()
                await self._run_input_loop(websocket, session)

            else:
                process = subprocess.Popen(
                    [shell_cmd],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(cwd),
                    text=False,
                    bufsize=0,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
                session = TerminalSession(session_id, "win_fallback", process, str(cwd), project_id=project_id)
                session.connected_sockets.append(websocket)
                self.active_sessions[session_id] = session

                def read_output():
                    try:
                        while session_id in self.active_sessions:
                            if process.stdout is None:
                                break
                            data = process.stdout.read(1024)
                            if not data:
                                break
                            text = data.decode("utf-8", errors="replace")
                            session.append_output(text)
                            for ws in list(session.connected_sockets):
                                try:
                                    future = asyncio.run_coroutine_threadsafe(ws.send_text(text), loop)
                                    future.result(timeout=5.0)
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.error("Error reading process output: %s", e)

                thread = threading.Thread(target=read_output, daemon=True)
                thread.start()
                await self._run_input_loop(websocket, session)

        except Exception as e:
            logger.error("Terminal connection error: %s", e)
            try:
                await websocket.close()
            except Exception:
                pass

    async def _run_input_loop(self, websocket: WebSocket, session: TerminalSession):
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                    action = msg.get("action")

                    if action == "input":
                        content = msg.get("data", "")
                        self._write_to_process(session, content)
                    elif action == "resize":
                        cols = msg.get("cols", 80)
                        rows = msg.get("rows", 24)
                        if session.session_type == "winpty":
                            session.process.set_size(cols, rows)
                        elif session.session_type == "unix_pty" and session.master_fd is not None:
                            try:
                                import fcntl
                                import termios
                                import struct
                                size = struct.pack("HHHH", rows, cols, 0, 0)
                                fcntl.ioctl(session.master_fd, termios.TIOCSWINSZ, size)
                            except Exception as resize_err:
                                logger.debug("Terminal resize error: %s", resize_err)
                    elif action == "interrupt":
                        self._send_interrupt(session)
                    elif action == "terminate":
                        self.terminate_session(session.session_id)
                        break
                except json.JSONDecodeError:
                    self._write_to_process(session, data)
        except WebSocketDisconnect:
            if websocket in session.connected_sockets:
                session.connected_sockets.remove(websocket)
            if len(session.connected_sockets) == 0:
                # Schedule graceful 10-minute cleanup
                session.cleanup_task = asyncio.create_task(self._graceful_cleanup(session.session_id, delay=600))
        except Exception as e:
            logger.debug("Terminal input loop error: %s", e)
            if websocket in session.connected_sockets:
                session.connected_sockets.remove(websocket)

    def _write_to_process(self, session: TerminalSession, content: str):
        if session.session_type == "winpty":
            session.process.write(content)
        elif session.session_type == "unix_pty" and session.master_fd is not None:
            os.write(session.master_fd, content.encode("utf-8"))
        elif session.process and session.process.stdin:
            session.process.stdin.write(content.encode("utf-8"))
            session.process.stdin.flush()

    def _send_interrupt(self, session: TerminalSession):
        if session.session_type == "winpty":
            session.process.write("\x03")
        elif session.session_type == "unix_pty":
            import signal
            os.killpg(os.getpgid(session.process.pid), signal.SIGINT)
        elif session.process:
            import signal
            os.kill(session.process.pid, signal.CTRL_C_EVENT)

manager = TerminalSessionManager()

@router.websocket("/ws/{project_id}")
async def terminal_websocket(
    websocket: WebSocket,
    project_id: str,
    ticket: str = Query(default=""),
    shell: str = Query(default="default"),
    session_id: Optional[str] = Query(default=None),
):
    """
    WebSocket terminal endpoint. Requires a valid short-lived JWT ticket passed as ?ticket=<ticket>.
    Optionally accepts a ?session_id=<id> to reattach to an existing persistent terminal process.
    """
    # Authenticate BEFORE accepting the connection
    from core.auth.auth_service import auth_service
    user_id = auth_service.verify_ws_ticket(ticket) if ticket else None
    if not user_id:
        await websocket.close(code=4001)
        logger.warning("Terminal WS rejected — missing or invalid ticket for project %s", project_id)
        return

    import uuid
    from sqlalchemy import select
    from core.memory.database import async_session
    from core.memory.models import Project

    async with async_session() as db:
        user = await auth_service.get_active_user(db, user_id)
        if not user:
            await websocket.close(code=4001)
            return
        from core.auth.instance_owner import assert_instance_owner
        from fastapi import HTTPException
        try:
            await assert_instance_owner({"sub": str(user.id)}, db)
        except HTTPException:
            await websocket.close(code=4003)
            return
        target_project_id = None
        if project_id and project_id != "default":
            try:
                project_uuid = uuid.UUID(project_id)
                project = (await db.execute(
                    select(Project.id).where(Project.id == project_uuid, Project.owner_id == user.id)
                )).scalar_one_or_none()
                if project:
                    target_project_id = str(project)
            except ValueError:
                target_project_id = None

        if not target_project_id and project_id == "default":
            # Fallback to user's first available project
            first_project = (await db.execute(
                select(Project.id).where(Project.owner_id == user.id).limit(1)
            )).scalar_one_or_none()
            if first_project:
                target_project_id = str(first_project)

        if not target_project_id:
            await websocket.close(code=4003)
            return

        project_id = target_project_id

    active_session_id = session_id or str(uuid.uuid4())
    logger.info(
        "Terminal WS opened: project=%s user=%s session=%s shell=%s",
        project_id, user_id, active_session_id, shell
    )
    await manager.connect(websocket, active_session_id, project_id, shell=shell)
