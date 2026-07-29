from fastapi import APIRouter, HTTPException, Query, Depends
import os
from pathlib import Path
from typing import List, Dict, Any

from core.tools.file_tools import file_tools
from core.auth.auth_middleware import require_auth

router = APIRouter(prefix="/api/files", tags=["files"])

from pydantic import BaseModel

class WriteFileRequest(BaseModel):
    path: str
    content: str
    project_id: str | None = None

class CreateFolderRequest(BaseModel):
    path: str
    project_id: str | None = None

class RenameRequest(BaseModel):
    source: str
    destination: str
    project_id: str | None = None

@router.get("/list")
async def list_files(path: str = Query(".", description="Relative path to directory"), project_id: str | None = Query(None, description="Project ID"), user: dict = Depends(require_auth)) -> List[Dict[str, Any]]:
    try:
        safe_path = await file_tools._resolve_safe_path(path, project_id)
        
        # Ensure root directory exists
        if path == "." or not safe_path.exists():
            if path == "." or str(safe_path) == str(await file_tools.get_workspace_root(project_id)):
                safe_path.mkdir(parents=True, exist_ok=True)
            else:
                raise HTTPException(status_code=404, detail=f"Directory '{path}' not found.")
                
        if not safe_path.is_dir():
            raise HTTPException(status_code=400, detail=f"'{path}' is not a directory.")
        
        root = await file_tools.get_workspace_root(project_id)
        result = []
        for item in sorted(os.listdir(safe_path)):
            full_item = safe_path / item
            is_dir = full_item.is_dir()
            size = full_item.stat().st_size if not is_dir else 0
            
            result.append({
                "name": item,
                "is_dir": is_dir,
                "size": size,
                "path": str(full_item.relative_to(root)).replace("\\", "/")
            })
            
        return result
    except HTTPException:
        raise
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/read")
async def read_file(path: str = Query(..., description="Relative path to file"), project_id: str | None = Query(None, description="Project ID"), user: dict = Depends(require_auth)) -> dict:
    try:
        safe_path = await file_tools._resolve_safe_path(path, project_id)
        if not safe_path.is_file():
            raise HTTPException(status_code=400, detail=f"'{path}' is not a file.")

        with open(safe_path, "r", encoding="utf-8") as f:
            content = f.read()

        return {"content": content}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Cannot read binary file.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Directories that bloat a file tree and are never useful as @-mention targets.
_TREE_IGNORE_DIRS = {
    "node_modules", ".git", ".next", "__pycache__", ".venv", "venv",
    "dist", "build", ".cache", ".mypy_cache", ".pytest_cache", "uploads",
    "file-history",
}
_TREE_MAX_FILES = 2000


@router.get("/tree")
async def file_tree(project_id: str | None = Query(None, description="Project ID"), team_id: str | None = Query(None, description="Team ID"), user: dict = Depends(require_auth)) -> dict:
    """Return a flat list of all file paths in the project workspace.

    Used to power @file mentions in chat. Sandbox-scoped to the project
    workspace (via file_tools.get_workspace_root) and excludes heavy /
    irrelevant directories. Capped at _TREE_MAX_FILES entries for safety.
    """
    try:
        import os
        from core.tools.file_tools import file_tools
        root = await file_tools.get_workspace_root(project_id)
        if not root.exists():
            return {"files": []}

        files: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune ignored dirs in-place so os.walk doesn't descend into them.
            dirnames[:] = [d for d in dirnames if d not in _TREE_IGNORE_DIRS and not d.startswith(".")]
            for name in filenames:
                if name.startswith("."):
                    continue
                full = os.path.join(dirpath, name)
                try:
                    rel = os.path.relpath(full, root).replace("\\", "/")
                except ValueError:
                    continue
                files.append(rel)
                if len(files) >= _TREE_MAX_FILES:
                    return {"files": files, "truncated": True}

        # Include media files for the specific team
        if team_id:
            team_carole_dir = await file_tools.get_team_carole_dir(team_id)
            chat_media_dir = team_carole_dir / "Chat_Media"
            if chat_media_dir.exists():
                for dirpath, dirnames, filenames in os.walk(chat_media_dir):
                    for name in filenames:
                        full = os.path.join(dirpath, name)
                        try:
                            rel = os.path.relpath(full, root).replace("\\", "/")
                        except ValueError:
                            continue
                        files.append(rel)
                        if len(files) >= _TREE_MAX_FILES:
                            return {"files": files, "truncated": True}

        return {"files": files, "truncated": False}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/write")
async def write_file_endpoint(req: WriteFileRequest, user: dict = Depends(require_auth)) -> dict:
    try:
        res = await file_tools.write_file(req.path, req.content, agent_name="User", project_id=req.project_id)
        if res.message.startswith("Error"):
            raise HTTPException(status_code=400, detail=res.message)
        return {"status": "success", "message": res.message}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create_folder")
async def create_folder_endpoint(req: CreateFolderRequest, user: dict = Depends(require_auth)) -> dict:
    try:
        res = await file_tools.create_directory(req.path, project_id=req.project_id)
        if res.startswith("Error"):
            raise HTTPException(status_code=400, detail=res)
        return {"status": "success", "message": res}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/rename")
async def rename_endpoint(req: RenameRequest, user: dict = Depends(require_auth)) -> dict:
    try:
        res = await file_tools.move_file(req.source, req.destination, project_id=req.project_id)
        if res.startswith("Error"):
            raise HTTPException(status_code=400, detail=res)
        return {"status": "success", "message": res}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete")
async def delete_file_endpoint(path: str = Query(...), project_id: str | None = Query(None), user: dict = Depends(require_auth)) -> dict:
    try:
        safe_path = await file_tools._resolve_safe_path(path, project_id)
        if safe_path.is_file():
            res = await file_tools.delete_file(path, agent_name="User", project_id=project_id)
            if res.startswith("Error"):
                raise HTTPException(status_code=400, detail=res)
        elif safe_path.is_dir():
            import shutil
            shutil.rmtree(safe_path)
            res = f"Success: Deleted directory '{path}'."
        else:
            raise HTTPException(status_code=404, detail="Path not found.")
            
        return {"status": "success", "message": res}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from sqlalchemy.ext.asyncio import AsyncSession
from core.memory.database import get_db

def _valid_uuid(value: str) -> bool:
    import uuid as _uuid
    try:
        _uuid.UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False

@router.get("/logs/{team_id}")
async def get_file_logs(team_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """Return recent file-change backups for a team.

    Hardened: validates the team_id UUID (returns 400 — not a 500 stack trace —
    for malformed input) and never raises on per-row read failures.
    """
    if not _valid_uuid(team_id):
        raise HTTPException(status_code=400, detail=f"Invalid team id '{team_id}'.")
    try:
        from core.memory.models import FileBackup, Message
        from sqlalchemy import select
        import uuid
        from pathlib import Path

        stmt = (
            select(FileBackup, Message.sender_name)
            .join(Message, Message.id == FileBackup.message_id)
            .where(FileBackup.team_id == uuid.UUID(team_id))
            .order_by(FileBackup.created_at.desc())
            .limit(100)
        )
        result = await db.execute(stmt)
        rows = result.all()

        logs = []
        from core.config import CAROLE_HOME_DIR
        for backup, sender_name in rows:
            current_content = ""
            try:
                with open(backup.file_path, "r", encoding="utf-8") as f:
                    current_content = f.read()
            except Exception:
                current_content = "[File Deleted or Binary]"

            # try to make path relative to workspace
            rel_path = backup.file_path
            try:
                rel_path = str(Path(backup.file_path).relative_to(CAROLE_HOME_DIR / "workspaces")).replace("\\", "/")
            except ValueError:
                pass

            original_content = ""
            if backup.backup_file_name:
                from core.tools.file_tools import file_tools
                team_carole_dir = await file_tools.get_team_carole_dir(team_id)
                history_dir = team_carole_dir / "file-history"
                backup_path = history_dir / backup.backup_file_name
                try:
                    if backup_path.exists():
                        with open(backup_path, "r", encoding="utf-8") as f:
                            original_content = f.read()
                except Exception:
                    original_content = "[Binary Backup]"

            logs.append({
                "id": str(backup.id),
                "file_path": rel_path,
                "operation": backup.operation,
                "agent_name": sender_name or "Agent",
                "original_content": original_content,
                "new_content": current_content,
                "timestamp": backup.created_at.isoformat() + "Z"
            })
        return logs
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger("carole.file_routes").exception("get_file_logs failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load activity log.")

@router.delete("/logs/{log_id}")
async def delete_file_log(log_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    if not _valid_uuid(log_id):
        raise HTTPException(status_code=400, detail=f"Invalid log id '{log_id}'.")
    from core.memory.models import FileBackup
    from sqlalchemy import select
    import uuid
    import os
    from core.config import CAROLE_HOME_DIR

    stmt = select(FileBackup).where(FileBackup.id == uuid.UUID(log_id))
    result = await db.execute(stmt)
    backup = result.scalar_one_or_none()

    if not backup:
        raise HTTPException(status_code=404, detail="Log not found")

    # Delete the physical backup file if it exists
    if backup.backup_file_name:
        from core.tools.file_tools import file_tools
        team_carole_dir = await file_tools.get_team_carole_dir(str(backup.team_id))
        history_dir = team_carole_dir / "file-history"
        backup_path = history_dir / backup.backup_file_name
        try:
            if backup_path.exists():
                os.remove(backup_path)
        except Exception as e:
            print(f"Warning: Failed to delete physical backup file: {e}")

    await db.delete(backup)
    await db.commit()
    return {"status": "success", "message": "File activity log deleted"}
