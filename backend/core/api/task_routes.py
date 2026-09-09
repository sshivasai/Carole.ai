from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from core.auth.auth_middleware import require_auth
from core.tools.shell_tools import process_registry
from core.memory.database import async_session
from core.api.crud_routes import _assert_team_access
from core.memory.models import Team, Project
from sqlalchemy import select
import uuid

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
    async with async_session() as db:
        if team_id:
            await _assert_team_access(db, team_id, user["sub"])
            allowed = {team_id}
        else:
            allowed = {str(team) for team in (await db.scalars(select(Team.id).join(
                Project, Project.id == Team.project_id).where(Project.owner_id == uuid.UUID(user["sub"])))).all()}
    return [task for task in process_registry.list_processes(team_id=team_id)
            if str(task.get("team_id")) in allowed]

@router.post("/{pid}/kill")
async def kill_task(
    pid: int,
    user: dict = Depends(require_auth)
):
    """
    Terminate a running task by PID.
    """
    await _owned_process(pid, user)
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
    await _owned_process(pid, user)
    success = process_registry.kill_process(pid)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or already terminated")
    return {"status": "success", "message": f"Task {pid} skipped"}


async def _owned_process(pid, user):
    process = next((row for row in process_registry.list_processes() if row["pid"] == pid), None)
    if not process or not process.get("team_id"):
        raise HTTPException(404, "Process not found")
    async with async_session() as db:
        await _assert_team_access(db, str(process["team_id"]), user["sub"])
