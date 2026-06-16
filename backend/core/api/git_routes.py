from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
import subprocess
from typing import Optional

from core.auth.auth_middleware import require_auth
from core.tools.file_tools import file_tools

router = APIRouter(prefix="/api/git", tags=["git"])

class GitCommitRequest(BaseModel):
    message: str
    project_id: Optional[str] = None

@router.get("/status")
async def get_git_status(project_id: str | None = Query(None), user: dict = Depends(require_auth)):
    try:
        workspace_root = await file_tools.get_workspace_root(project_id)
        
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            return {"status": "success", "changes": [], "message": "No git repository or git error."}
            
        changes = []
        for line in result.stdout.split("\n"):
            if not line.strip():
                continue
            status = line[:2]
            file_path = line[3:]
            changes.append({
                "file": file_path,
                "status": status.strip()
            })
            
        return {"status": "success", "changes": changes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/commit")
async def commit_changes(req: GitCommitRequest, user: dict = Depends(require_auth)):
    try:
        workspace_root = await file_tools.get_workspace_root(req.project_id)
        
        # Add all
        subprocess.run(["git", "add", "."], cwd=workspace_root, check=True)
        
        # Commit
        res = subprocess.run(
            ["git", "commit", "-m", req.message],
            cwd=workspace_root,
            capture_output=True,
            text=True
        )
        
        if res.returncode != 0:
            # Usually means nothing to commit
            return {"status": "error", "message": res.stderr or res.stdout or "Commit failed"}
            
        return {"status": "success", "message": "Changes committed successfully."}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Git command failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
