from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import subprocess
import threading
import sys
import os
import json
import logging
from typing import Dict, Any

try:
    import winpty
    HAS_WINPTY = True
except ImportError:
    HAS_WINPTY = False

from core.tools.file_tools import file_tools

router = APIRouter(prefix="/api/terminal", tags=["terminal"])
logger = logging.getLogger(__name__)

class TerminalSessionManager:
    def __init__(self):
        self.active_sessions: Dict[str, Any] = {}

    async def connect(self, websocket: WebSocket, session_id: str, project_id: str | None = None):
        await websocket.accept()
        
        # Get the working directory for this project
        cwd = await file_tools.get_workspace_root(project_id)
        if not cwd.exists():
            cwd.mkdir(parents=True, exist_ok=True)
            
        try:
            if sys.platform == "win32" and HAS_WINPTY:
                # Use winpty for a true PTY experience on Windows
                process = winpty.PTY(80, 24)
                # cmd.exe is the default on Windows
                process.spawn('cmd.exe', cwd=str(cwd))
                self.active_sessions[session_id] = process
                
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
                                break  # WebSocket closed or sending failed
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
                                # pywinpty doesn't have an explicit interrupt method
                                # Ctrl+C is sent as '\x03' via input usually
                                process.write('\x03')
                        except json.JSONDecodeError:
                            process.write(data)
                except WebSocketDisconnect:
                    self.disconnect(session_id)
            else:
                # Fallback for non-Windows or if winpty is not installed
                shell = os.environ.get("COMSPEC", "cmd.exe") if sys.platform == "win32" else os.environ.get("SHELL", "/bin/bash")
                process = subprocess.Popen(
                    shell,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(cwd),
                    text=False,
                    bufsize=0,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                )
                self.active_sessions[session_id] = process
                
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
                                if sys.platform == "win32":
                                    import signal
                                    os.kill(process.pid, signal.CTRL_C_EVENT)
                                else:
                                    process.send_signal(subprocess.signal.SIGINT)
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
        process = self.active_sessions.pop(session_id, None)
        if process:
            try:
                if hasattr(process, 'terminate'):
                    process.terminate()
                else:
                    del process # winpty object
            except Exception:
                pass

manager = TerminalSessionManager()

@router.websocket("/ws/{project_id}")
async def terminal_websocket(websocket: WebSocket, project_id: str):
    import uuid
    session_id = str(uuid.uuid4())
    await manager.connect(websocket, session_id, project_id)
