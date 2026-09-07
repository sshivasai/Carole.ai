from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
import subprocess
import os
from typing import Optional, List

from core.auth.auth_middleware import require_auth
from core.tools.file_tools import file_tools

from sqlalchemy.ext.asyncio import AsyncSession
from core.memory.database import get_db

router = APIRouter(prefix="/api/git", tags=["git"])

class GitCommitRequest(BaseModel):
    message: str
    project_id: Optional[str] = None
    slug: Optional[str] = None

class GitActionRequest(BaseModel):
    file: str
    project_id: Optional[str] = None
    slug: Optional[str] = None

async def _assert_git_project_access(project_id_or_slug: Optional[str], user_id: str, db: Optional[AsyncSession] = None) -> None:
    if not project_id_or_slug:
        return
    import uuid
    import re
    from core.memory.models import Project
    from sqlalchemy import select
    from core.api.crud_routes import _assert_project_access

    if db is not None:
        session = db
        try:
            uuid.UUID(str(project_id_or_slug))
            await _assert_project_access(session, str(project_id_or_slug), user_id)
            return
        except ValueError:
            pass

        res = await session.execute(select(Project))
        projects = res.scalars().all()
        matched_proj = None
        for p in projects:
            slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', p.name).strip('-')
            if slug.lower() == str(project_id_or_slug).lower() or p.name.lower() == str(project_id_or_slug).lower():
                matched_proj = p
                break
        if matched_proj:
            await _assert_project_access(session, str(matched_proj.id), user_id)
    else:
        from core.memory.database import async_session
        try:
            uuid.UUID(str(project_id_or_slug))
            async with async_session() as session:
                await _assert_project_access(session, str(project_id_or_slug), user_id)
            return
        except ValueError:
            pass

        async with async_session() as session:
            res = await session.execute(select(Project))
            projects = res.scalars().all()
            matched_proj = None
            for p in projects:
                slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', p.name).strip('-')
                if slug.lower() == str(project_id_or_slug).lower() or p.name.lower() == str(project_id_or_slug).lower():
                    matched_proj = p
                    break
            if matched_proj:
                await _assert_project_access(session, str(matched_proj.id), user_id)


@router.post("/init")
async def init_repository(
    slug: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await _assert_git_project_access(project_id or slug, user["sub"], db=db)
    try:
        workspace_root = await file_tools.get_workspace_root(project_id or slug)
        res = subprocess.run(
            ["git", "init"],
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            check=True
        )
        
        # Auto-create/update .gitignore to ignore the .carole folder
        gitignore_path = os.path.join(workspace_root, ".gitignore")
        has_carole = False
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines()]
                if ".carole/" in lines or ".carole" in lines:
                    has_carole = True
                    
        if not has_carole:
            mode = "a" if os.path.exists(gitignore_path) else "w"
            with open(gitignore_path, mode, encoding="utf-8") as f:
                # Add newline before if appending
                prefix = "\n" if mode == "a" else ""
                f.write(f"{prefix}# Carole.ai internal directory\n.carole/\n")
                
        return {"status": "success", "message": "Repository initialized and .gitignore updated."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_git_status(
    slug: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await _assert_git_project_access(project_id or slug, user["sub"], db=db)
    try:
        workspace_root = await file_tools.get_workspace_root(project_id or slug)
        
        # Check if git repository exists
        if not os.path.exists(os.path.join(workspace_root, ".git")):
            return {"status": "success", "changes": [], "message": "Not a git repository. Initialize it first."}

        # Run git status porcelain
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            return {"status": "success", "changes": [], "message": f"Git error: {result.stderr or result.stdout}"}
            
        changes = []
        for line in result.stdout.split("\n"):
            if not line.strip():
                continue
            # Git porcelain status line format: XY file_path
            # X = status index (staged changes)
            # Y = status work tree (unstaged changes)
            x_status = line[0]
            y_status = line[1]
            file_path = line[3:]

            # Parse status
            # If there are both staged and unstaged changes, we yield both
            is_staged = x_status != " " and x_status != "?"
            is_unstaged = y_status != " "
            
            # Map code symbols
            status_char = "M"
            if x_status == "A" or y_status == "A" or x_status == "?" or y_status == "?":
                status_char = "A"
            elif x_status == "D" or y_status == "D":
                status_char = "D"
            
            if x_status == "R" or y_status == "R":
                status_char = "R"

            changes.append({
                "file": file_path,
                "status": status_char,
                "staged": is_staged,
                "unstaged": is_unstaged,
                "raw_x": x_status,
                "raw_y": y_status
            })
            
        return {"status": "success", "changes": changes}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stage")
async def stage_file(
    req: GitActionRequest,
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await _assert_git_project_access(req.project_id or req.slug, user["sub"], db=db)
    try:
        workspace_root = await file_tools.get_workspace_root(req.project_id or req.slug)
        res = subprocess.run(
            ["git", "add", req.file],
            cwd=str(workspace_root),
            capture_output=True,
            text=True
        )
        if res.returncode != 0:
            return {"status": "error", "message": res.stderr or "Failed to stage file"}
        return {"status": "success", "message": f"Staged {req.file}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/unstage")
async def unstage_file(
    req: GitActionRequest,
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await _assert_git_project_access(req.project_id or req.slug, user["sub"], db=db)
    try:
        workspace_root = await file_tools.get_workspace_root(req.project_id or req.slug)
        # Check if HEAD exists (if not, we reset using git rm --cached)
        head_check = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=str(workspace_root),
            capture_output=True
        )
        if head_check.returncode == 0:
            cmd = ["git", "restore", "--staged", req.file]
        else:
            cmd = ["git", "rm", "--cached", req.file]

        res = subprocess.run(
            cmd,
            cwd=str(workspace_root),
            capture_output=True,
            text=True
        )
        if res.returncode != 0:
            return {"status": "error", "message": res.stderr or "Failed to unstage file"}
        return {"status": "success", "message": f"Unstaged {req.file}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/discard")
async def discard_changes(
    req: GitActionRequest,
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await _assert_git_project_access(req.project_id or req.slug, user["sub"], db=db)
    try:
        workspace_root = await file_tools.get_workspace_root(req.project_id or req.slug)
        
        # Check if file is untracked
        status_res = subprocess.run(
            ["git", "status", "--porcelain", req.file],
            cwd=str(workspace_root),
            capture_output=True,
            text=True
        )
        is_untracked = False
        if status_res.stdout.startswith("??"):
            is_untracked = True

        if is_untracked:
            # For untracked files, discard means delete
            full_path = os.path.join(workspace_root, req.file)
            if os.path.exists(full_path):
                if os.path.isdir(full_path):
                    import shutil
                    shutil.rmtree(full_path)
                else:
                    os.remove(full_path)
            return {"status": "success", "message": f"Deleted untracked file {req.file}"}
        else:
            # For tracked files, restore working tree changes
            res = subprocess.run(
                ["git", "restore", req.file],
                cwd=str(workspace_root),
                capture_output=True,
                text=True
            )
            if res.returncode != 0:
                return {"status": "error", "message": res.stderr or "Failed to discard changes"}
            return {"status": "success", "message": f"Discarded changes for {req.file}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ignore")
async def add_to_gitignore(
    req: GitActionRequest,
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await _assert_git_project_access(req.project_id or req.slug, user["sub"], db=db)
    try:
        workspace_root = await file_tools.get_workspace_root(req.project_id or req.slug)
        gitignore_path = os.path.join(workspace_root, ".gitignore")
        
        with open(gitignore_path, "a") as f:
            f.write(f"\n{req.file}\n")
            
        return {"status": "success", "message": f"Added {req.file} to .gitignore"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/commit")
async def commit_changes(
    req: GitCommitRequest,
    slug: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await _assert_git_project_access(req.project_id or req.slug or project_id or slug, user["sub"], db=db)
    try:
        workspace_root = await file_tools.get_workspace_root(req.project_id or req.slug or project_id or slug)
        
        # Commit staged files
        res = subprocess.run(
            ["git", "commit", "-m", req.message],
            cwd=str(workspace_root),
            capture_output=True,
            text=True
        )
        
        if res.returncode != 0:
            # Try to commit all changes if nothing is staged
            # (VS Code does this or prompts to stage all if nothing is staged)
            # But let's run git commit -a -m message if they had unstaged changes
            res_all = subprocess.run(
                ["git", "commit", "-a", "-m", req.message],
                cwd=str(workspace_root),
                capture_output=True,
                text=True
            )
            if res_all.returncode != 0:
                return {"status": "error", "message": res_all.stderr or res.stdout or "Commit failed. Stage changes first."}
            return {"status": "success", "message": "Changes committed successfully (staged all first)."}
            
        return {"status": "success", "message": "Staged changes committed successfully."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/show")
async def show_git_file(
    file: str,
    slug: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await _assert_git_project_access(project_id or slug, user["sub"], db=db)
    try:
        workspace_root = await file_tools.get_workspace_root(project_id or slug)
        res = subprocess.run(
            ["git", "show", f"HEAD:{file}"],
            cwd=str(workspace_root),
            capture_output=True,
            text=True
        )
        if res.returncode != 0:
            # File might be untracked or HEAD doesn't exist
            return {"status": "success", "content": ""}
        return {"status": "success", "content": res.stdout}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/log")
async def get_commit_history(
    slug: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    limit: int = Query(50),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await _assert_git_project_access(project_id or slug, user["sub"], db=db)
    try:
        workspace_root = await file_tools.get_workspace_root(project_id or slug)
        
        # Check if git repository exists
        if not os.path.exists(os.path.join(workspace_root, ".git")):
            return {"status": "success", "commits": [], "message": "Not a git repository."}

        # Run git log with custom format
        # Format: hash|author|date(iso)|message
        res = subprocess.run(
            ["git", "log", f"-n", str(limit), "--pretty=format:%h|%an|%ad|%s", "--date=short"],
            cwd=str(workspace_root),
            capture_output=True,
            text=True
        )
        if res.returncode != 0:
            # Could mean no commits yet
            return {"status": "success", "commits": [], "message": "No commits found."}
            
        commits = []
        for line in res.stdout.split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 3)
            if len(parts) >= 4:
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3]
                })
            elif len(parts) == 1:
                # Fallback if split failed or format is weird
                commits.append({
                    "hash": "unknown",
                    "author": "unknown",
                    "date": "unknown",
                    "message": parts[0]
                })
                
        return {"status": "success", "commits": commits}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class GitCheckpointCreateRequest(BaseModel):
    message: Optional[str] = "Manual Checkpoint"
    project_id: Optional[str] = None
    slug: Optional[str] = None


class GitCheckpointRollbackRequest(BaseModel):
    checkpoint_id: str
    project_id: Optional[str] = None
    slug: Optional[str] = None


@router.post("/checkpoint/create")
async def create_checkpoint(
    req: GitCheckpointCreateRequest,
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await _assert_git_project_access(req.project_id or req.slug, user["sub"], db=db)
    try:
        from core.tools.git_tools import git_tools
        workspace_root = await file_tools.get_workspace_root(req.project_id or req.slug)
        result = await git_tools.create_checkpoint(name=req.message or "Manual Checkpoint", cwd=str(workspace_root))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/checkpoints")
async def list_checkpoints(
    slug: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await _assert_git_project_access(project_id or slug, user["sub"], db=db)
    try:
        from core.tools.git_tools import git_tools
        workspace_root = await file_tools.get_workspace_root(project_id or slug)
        checkpoints = await git_tools.list_checkpoints(cwd=str(workspace_root))
        return {"status": "success", "checkpoints": checkpoints}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/checkpoint/rollback")
async def rollback_checkpoint(
    req: GitCheckpointRollbackRequest,
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await _assert_git_project_access(req.project_id or req.slug, user["sub"], db=db)
    try:
        from core.tools.git_tools import git_tools
        workspace_root = await file_tools.get_workspace_root(req.project_id or req.slug)
        result = await git_tools.rollback_checkpoint(req.checkpoint_id, cwd=str(workspace_root))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/checkpoint/diff")
async def diff_checkpoint(
    checkpoint_id: str = Query(...),
    slug: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await _assert_git_project_access(project_id or slug, user["sub"], db=db)
    try:
        from core.tools.git_tools import git_tools
        workspace_root = await file_tools.get_workspace_root(project_id or slug)
        result = await git_tools.diff_checkpoint(checkpoint_id, cwd=str(workspace_root))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


