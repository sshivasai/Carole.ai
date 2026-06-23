from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.auth.auth_middleware import require_auth
from core.tools.shell_tools import shell_tools

router = APIRouter(prefix="/api/terminal", tags=["terminal"])

class TerminalExecuteRequest(BaseModel):
    command: str
    project_id: Optional[str] = None
    timeout: float = 60.0

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
        result = await shell_tools.execute_command(req.command, team_id, req.timeout, cwd=cwd)

        return {"status": "success", "output": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
