from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
import subprocess
from typing import Optional, List

from core.auth.auth_middleware import require_auth
from core.tools.file_tools import file_tools

router = APIRouter(prefix="/api/search", tags=["search"])

@router.get("/grep")
async def search_files(
    q: str = Query(..., description="The search string or pattern"),
    project_id: str | None = Query(None, description="Project ID"),
    user: dict = Depends(require_auth)
):
    try:
        workspace_root = await file_tools.get_workspace_root(project_id)
        
        # We can use git grep or ripgrep if available, or just standard grep
        # Let's use `git grep` since it automatically ignores .gitignore and is fast
        # If it fails, fallback to something else or just standard grep
        
        # `-n` for line numbers, `-I` for ignoring binary files
        res = subprocess.run(
            ["git", "grep", "-n", "-I", q],
            cwd=workspace_root,
            capture_output=True,
            text=True
        )
        
        if res.returncode != 0 and res.returncode != 1:
             return {"status": "error", "message": "Search failed"}
             
        results = []
        if res.stdout:
            for line in res.stdout.split("\n"):
                if not line:
                    continue
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    file_path = parts[0]
                    line_num = parts[1]
                    content = parts[2]
                    results.append({
                        "file": file_path,
                        "line": line_num,
                        "content": content.strip()
                    })
        
        return {"status": "success", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
