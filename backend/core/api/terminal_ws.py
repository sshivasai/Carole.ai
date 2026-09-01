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
from core.auth.auth_service import _decode_jwt

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

class TerminalSessionManager:
    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket, session_id: str, project_id: Optional[str] = None, shell: str = "default"):
        await websocket.accept()
        
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
            else:  # default or unix shell
                shell_cmd = os.environ.get("SHELL", "/bin/bash")

        try:
            if sys.platform == "win32" and HAS_WINPTY:
                # Winpty on Windows
                process = winpty.PTY(80, 24)
                process.spawn(shell_cmd, cwd=str(cwd))
                self.active_sessions[session_id] = {"type": "winpty", "process": process}
                
                loop = asyncio.get_running_loop()
                
                def read_output_winpty():
                    try:
                        while session_id in self.active_sessions and process.isalive():
                            data = process.read(blocking=True)
                            if not data:
                                break
                            future = asyncio.run_coroutine_threadsafe(
                                websocket.send_text(data), 
                                loop
                            )
                            try:
                                future.result(timeout=5.0)
                            except Exception:
                                break
                    except Exception as e:
                        logger.debug("Winpty reader exiting: %s", e)
                            
                thread = threading.Thread(target=read_output_winpty, daemon=True)
                thread.start()
                
                try:
                    while True:
                        data = await websocket.receive_text()
                        try:
                            msg = json.loads(data)
                            action = msg.get("action")
                            
                            if action == "input":
                                content = msg.get("data", "")
                                process.write(content)
                            elif action == "resize":
                                cols = msg.get("cols", 80)
                                rows = msg.get("rows", 24)
                                process.set_size(cols, rows)
                            elif action == "interrupt":
                                process.write('\x03')
                        except json.JSONDecodeError:
                            process.write(data)
                except WebSocketDisconnect:
                    self.disconnect(session_id)
            elif sys.platform != "win32":
                # True interactive Unix PTY for macOS and Linux
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
                
                self.active_sessions[session_id] = {"type": "unix_pty", "process": process, "master_fd": master_fd}
                
                loop = asyncio.get_running_loop()
                
                def read_output_pty():
                    try:
                        while session_id in self.active_sessions:
                            data = os.read(master_fd, 1024)
                            if not data:
                                break
                            future = asyncio.run_coroutine_threadsafe(
                                websocket.send_text(data.decode('utf-8', errors='replace')),
                                loop
                            )
                            try:
                                future.result(timeout=5.0)
                            except Exception:
                                break
                    except Exception as e:
                        logger.debug("Unix PTY reader exiting: %s", e)
                    finally:
                        try:
                            os.close(master_fd)
                        except Exception:
                            pass
                            
                thread = threading.Thread(target=read_output_pty, daemon=True)
                thread.start()
                
                try:
                    while True:
                        data = await websocket.receive_text()
                        try:
                            msg = json.loads(data)
                            action = msg.get("action")
                            
                            if action == "input":
                                content = msg.get("data", "")
                                os.write(master_fd, content.encode('utf-8'))
                            elif action == "resize":
                                cols = msg.get("cols", 80)
                                rows = msg.get("rows", 24)
                                size = struct.pack("HHHH", rows, cols, 0, 0)
                                fcntl.ioctl(master_fd, termios.TIOCSWINSZ, size)
                            elif action == "interrupt":
                                os.killpg(os.getpgid(process.pid), 2)  # SIGINT
                        except json.JSONDecodeError:
                            os.write(master_fd, data.encode('utf-8'))
                except WebSocketDisconnect:
                    self.disconnect(session_id)
            else:
                # Windows fallback (Popen) without Winpty
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
                self.active_sessions[session_id] = {"type": "win_fallback", "process": process}
                
                loop = asyncio.get_running_loop()
                
                def read_output():
                    try:
                        while True:
                            if process.stdout is None:
                                break
                            data = process.stdout.read(1024)
                            if not data:
                                break
                            asyncio.run_coroutine_threadsafe(
                                websocket.send_text(data.decode('utf-8', errors='replace')), 
                                loop
                            )
                    except Exception as e:
                        logger.error(f"Error reading process output: {e}")
                    finally:
                        if process.poll() is None:
                            process.terminate()
                            
                thread = threading.Thread(target=read_output, daemon=True)
                thread.start()
                
                try:
                    while True:
                        data = await websocket.receive_text()
                        try:
                            msg = json.loads(data)
                            action = msg.get("action")
                            
                            if action == "input" and process.stdin:
                                content = msg.get("data", "")
                                process.stdin.write(content.encode('utf-8'))
                                process.stdin.flush()
                            elif action == "resize":
                                pass
                            elif action == "interrupt":
                                import signal
                                os.kill(process.pid, signal.CTRL_C_EVENT)
                        except json.JSONDecodeError:
                            if process.stdin:
                                process.stdin.write(data.encode('utf-8'))
                                process.stdin.flush()
                except WebSocketDisconnect:
                    self.disconnect(session_id)
        except Exception as e:
            logger.error(f"Terminal connection error: {e}")
            await websocket.close()

    def disconnect(self, session_id: str):
        session = self.active_sessions.pop(session_id, None)
        if not session:
            return
            
        session_type = session.get("type")
        process = session.get("process")
        
        if session_type == "unix_pty":
            master_fd = session.get("master_fd")
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except Exception:
                    pass
                    
        if process:
            # Terminate the process tree cleanly to kill all background server child tasks
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
                else:
                    import signal
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except Exception:
                try:
                    if hasattr(process, 'terminate'):
                        process.terminate()
                    elif hasattr(process, 'close'):
                        process.close()
                except Exception:
                    pass

manager = TerminalSessionManager()

@router.websocket("/ws/{project_id}")
async def terminal_websocket(
    websocket: WebSocket,
    project_id: str,
    ticket: str = Query(default=""),
    shell: str = Query(default="default"),
):
    """
    WebSocket terminal endpoint. Requires a valid short-lived JWT ticket passed as ?ticket=<ticket>.
    """
    # Authenticate BEFORE accepting the connection
    from core.auth.auth_service import auth_service
    user_id = auth_service.verify_ws_ticket(ticket) if ticket else None
    if not user_id:
        await websocket.close(code=4001)
        logger.warning("Terminal WS rejected — missing or invalid ticket for project %s", project_id)
        return

    import uuid
    session_id = str(uuid.uuid4())
    logger.info(
        "Terminal WS opened: project=%s user=%s session=%s shell=%s",
        project_id, user_id, session_id, shell
    )
    await manager.connect(websocket, session_id, project_id, shell=shell)
