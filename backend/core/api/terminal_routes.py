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
        # Since shell_tools currently uses workspace_root for cwd, we might need to change it 
        # to respect project_id if needed, but for now we just pass the command.
        
        # We'll patch shell_tools to support project_id if it doesn't already, but for now
        # let's just run it.
        result = await shell_tools.execute_command(req.command, team_id, req.timeout)
        
        return {"status": "success", "output": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
