from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.auth.auth_middleware import require_auth
from core.tools.shell_tools import shell_tools, process_registry

router = APIRouter(prefix="/api/terminal", tags=["terminal"])

class TerminalExecuteRequest(BaseModel):
    command: str
    project_id: Optional[str] = None
    timeout: float = 60.0
    background: bool = False

@router.post("/execute")
async def execute_command(req: TerminalExecuteRequest, user: dict = Depends(require_auth)):
    try:
        # Use project_id as team_id for websocket streaming
        team_id = req.project_id or "default"
        # Scope the command to the project workspace so user-run terminal
        # commands also stay inside the right sandbox (mirrors agent behavior).
        cwd = None
        if req.project_id:
            from core.tools.file_tools import file_tools as _ft
            cwd = str(await _ft.get_workspace_root(req.project_id))
        result = await shell_tools.execute_command(
            req.command, team_id, req.timeout, cwd=cwd, background=req.background
        )

        return {"status": "success", "output": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/processes")
async def list_processes(project_id: Optional[str] = None, user: dict = Depends(require_auth)):
    """List active and recently executed background processes."""
    return process_registry.list_processes(team_id=project_id)


@router.post("/kill/{pid}")
async def kill_process(pid: int, user: dict = Depends(require_auth)):
    """Kill an active background or foreground process by its PID."""
    killed = process_registry.kill_process(pid)
    if killed:
        return {"status": "success", "message": f"Process {pid} terminated successfully."}
    return {"status": "not_found", "message": f"Process {pid} was not found or has already terminated."}
