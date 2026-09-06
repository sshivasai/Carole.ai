from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from core.auth.auth_middleware import require_auth
from core.tools.shell_tools import process_registry

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

class TaskInfo(BaseModel):
    pid: int
    command: str
    team_id: str
    cwd: str
    background: bool
    status: str
    started_at: str
    returncode: Optional[int] = None

@router.get("", response_model=List[TaskInfo])
async def list_tasks(
    team_id: Optional[str] = Query(None, description="Filter tasks by team_id"),
    user: dict = Depends(require_auth)
):
    """
    List all running and recently terminated processes tracked by the system.
    """
    tasks = process_registry.list_processes(team_id=team_id)
    return tasks

@router.post("/{pid}/kill")
async def kill_task(
    pid: int,
    user: dict = Depends(require_auth)
):
    """
    Terminate a running task by PID.
    """
    success = process_registry.kill_process(pid)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or already terminated")
    return {"status": "success", "message": f"Task {pid} terminated"}

@router.post("/{pid}/skip")
async def skip_task(
    pid: int,
    user: dict = Depends(require_auth)
):
    """
    Skip a task (essentially same as kill but allows UI to mark it skipped).
    """
    success = process_registry.kill_process(pid)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or already terminated")
    return {"status": "success", "message": f"Task {pid} skipped"}
