from fastapi import APIRouter, HTTPException, Query, Depends, Header
from fastapi.responses import StreamingResponse, FileResponse
import os
import io
import shutil
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from core.tools.file_tools import file_tools
from core.auth.auth_middleware import require_auth

router = APIRouter(prefix="/api/files", tags=["files"])


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

class CopyRequest(BaseModel):
    source: str
    destination: str
    project_id: str | None = None

class DuplicateRequest(BaseModel):
    path: str
    project_id: str | None = None

class BatchCopyRequest(BaseModel):
    sources: List[str]
    destination_dir: str = "."
    project_id: str | None = None

class BatchMoveRequest(BaseModel):
    sources: List[str]
    destination_dir: str = "."
    project_id: str | None = None

class BatchDeleteRequest(BaseModel):
    paths: List[str]
    project_id: str | None = None


async def _broadcast_file_event(action: str, paths: List[str], project_id: Optional[str] = None, team_id: Optional[str] = None, diff: Optional[str] = None, user: Optional[dict] = None):
    """Broadcasts file system mutation events over the EventBus to all subscribers."""
    try:
        from core.chat.event_bus import event_bus
        
        user_name = "User"
        user_id = "human"
        if user and "sub" in user:
            user_id = user["sub"]
            from core.memory.database import async_session
            from core.memory.models import User as DBUser
            from sqlalchemy import select
            import uuid
            try:
                user_uuid = uuid.UUID(user["sub"])
                async with async_session() as db:
                    stmt = select(DBUser).where(DBUser.id == user_uuid)
                    db_user = (await db.execute(stmt)).scalar_one_or_none()
                    if db_user:
                        parts = []
                        if db_user.first_name:
                            parts.append(db_user.first_name)
                        if db_user.last_name:
                            parts.append(db_user.last_name)
                        if parts:
                            user_name = " ".join(parts)
                        else:
                            user_name = db_user.email.split("@")[0]
            except Exception:
                pass

        evt = {
            "type": "file_system_updated",
            "action": action,
            "paths": paths,
            "path": paths[0] if paths else "",
            "project_id": project_id,
            "diff": diff,
            "sender_id": user_id,
            "sender_name": user_name,
            "_seq": int(os.times().system * 1000) if hasattr(os, "times") else 0,
        }
        if project_id:
            await event_bus.publish(f"project:{project_id}", evt)
        if team_id:
            await event_bus.publish(f"team:{team_id}", evt)
        await event_bus.publish("system:file_changes", evt)

        # Also emit standard file_change event for real-time editor and activity logs
        file_change_evt = {
            "type": "file_change",
            "action": action,
            "path": paths[0] if paths else "",
            "paths": paths,
            "project_id": project_id,
            "diff": diff or "",
            "sender_id": user_id,
            "sender_name": user_name,
        }
        if project_id:
            await event_bus.publish(f"project:{project_id}", file_change_evt)
        if team_id:
            await event_bus.publish(f"team:{team_id}", file_change_evt)
        await event_bus.publish("system:file_changes", file_change_evt)
    except Exception as e:
        import logging
        logging.getLogger("carole.files").warning(f"File broadcast error: {e}")


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
            mtime = full_item.stat().st_mtime if full_item.exists() else 0
            
            result.append({
                "name": item,
                "is_dir": is_dir,
                "size": size,
                "mtime": mtime,
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

        content = await file_tools.read_file(path, project_id, force=True)
        if content.startswith("Error"):
            raise HTTPException(status_code=400, detail=content)

        return {"content": content}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/raw")
async def get_raw_file(
    path: str = Query(..., description="Relative path to file"),
    project_id: Optional[str] = Query(None, description="Project ID"),
    token: Optional[str] = Query(None, description="Auth token via query parameter"),
    authorization: Optional[str] = Header(None, description="Auth token via Header")
):
    # Check auth header first, fall back to query token
    auth_token = None
    if authorization and authorization.startswith("Bearer "):
        auth_token = authorization[7:]
    elif token:
        auth_token = token
        
    if not auth_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    from core.auth.auth_service import _decode_jwt
    payload = _decode_jwt(auth_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
        
    try:
        safe_path = await file_tools._resolve_safe_path(path, project_id)
        if not safe_path.is_file():
            raise HTTPException(status_code=400, detail=f"'{path}' is not a file.")
        
        if not safe_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
            
        return FileResponse(path=safe_path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
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
    """Return a flat list of all file paths in the project workspace."""
    try:
        root = await file_tools.get_workspace_root(project_id)
        if not root.exists():
            return {"files": []}

        files: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
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
        await _broadcast_file_event("write", [req.path], project_id=req.project_id, diff=res.diff, user=user)
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
        await _broadcast_file_event("create_folder", [req.path], project_id=req.project_id, user=user)
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
        await _broadcast_file_event("rename", [req.source, req.destination], project_id=req.project_id, user=user)
        return {"status": "success", "message": res}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/copy")
async def copy_endpoint(req: CopyRequest, user: dict = Depends(require_auth)) -> dict:
    try:
        src = await file_tools._resolve_safe_path(req.source, req.project_id)
        dst = await file_tools._resolve_safe_path(req.destination, req.project_id)
        if not src.exists():
            raise HTTPException(status_code=404, detail=f"Source '{req.source}' not found.")
        
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_file():
            shutil.copy2(str(src), str(dst))
        else:
            shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
            
        await _broadcast_file_event("copy", [req.destination], project_id=req.project_id, user=user)
        return {"status": "success", "message": f"Copied '{req.source}' to '{req.destination}'"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/duplicate")
async def duplicate_endpoint(req: DuplicateRequest, user: dict = Depends(require_auth)) -> dict:
    try:
        safe_path = await file_tools._resolve_safe_path(req.path, req.project_id)
        if not safe_path.exists():
            raise HTTPException(status_code=404, detail=f"Path '{req.path}' not found.")
        
        parent = safe_path.parent
        stem = safe_path.stem
        suffix = safe_path.suffix
        
        counter = 1
        new_name = f"{stem} (copy){suffix}"
        while (parent / new_name).exists():
            counter += 1
            new_name = f"{stem} (copy {counter}){suffix}"
            
        root = await file_tools.get_workspace_root(req.project_id)
        dst_rel = str((parent / new_name).relative_to(root)).replace("\\", "/")
        
        if safe_path.is_file():
            shutil.copy2(str(safe_path), str(parent / new_name))
        else:
            shutil.copytree(str(safe_path), str(parent / new_name))
            
        await _broadcast_file_event("duplicate", [dst_rel], project_id=req.project_id, user=user)
        return {"status": "success", "new_path": dst_rel}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch/copy")
async def batch_copy_endpoint(req: BatchCopyRequest, user: dict = Depends(require_auth)) -> dict:
    try:
        copied = []
        root = await file_tools.get_workspace_root(req.project_id)
        dst_dir_path = await file_tools._resolve_safe_path(req.destination_dir, req.project_id)
        dst_dir_path.mkdir(parents=True, exist_ok=True)
        
        for src_rel in req.sources:
            src_safe = await file_tools._resolve_safe_path(src_rel, req.project_id)
            if not src_safe.exists():
                continue
            item_name = src_safe.name
            target_path = dst_dir_path / item_name
            # If target already exists, append _copy
            if target_path.exists():
                stem = target_path.stem
                suffix = target_path.suffix
                target_path = dst_dir_path / f"{stem}_copy{suffix}"
                
            if src_safe.is_file():
                shutil.copy2(str(src_safe), str(target_path))
            else:
                shutil.copytree(str(src_safe), str(target_path), dirs_exist_ok=True)
            copied.append(str(target_path.relative_to(root)).replace("\\", "/"))
            
        await _broadcast_file_event("batch_copy", copied, project_id=req.project_id, user=user)
        return {"status": "success", "copied": copied}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch/move")
async def batch_move_endpoint(req: BatchMoveRequest, user: dict = Depends(require_auth)) -> dict:
    try:
        moved = []
        root = await file_tools.get_workspace_root(req.project_id)
        dst_dir_path = await file_tools._resolve_safe_path(req.destination_dir, req.project_id)
        dst_dir_path.mkdir(parents=True, exist_ok=True)
        
        for src_rel in req.sources:
            src_safe = await file_tools._resolve_safe_path(src_rel, req.project_id)
            if not src_safe.exists():
                continue
            item_name = src_safe.name
            target_path = dst_dir_path / item_name
            if target_path == src_safe:
                continue
            shutil.move(str(src_safe), str(target_path))
            moved.append(str(target_path.relative_to(root)).replace("\\", "/"))
            
        await _broadcast_file_event("batch_move", moved, project_id=req.project_id, user=user)
        return {"status": "success", "moved": moved}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch/delete")
async def batch_delete_endpoint(req: BatchDeleteRequest, user: dict = Depends(require_auth)) -> dict:
    try:
        deleted = []
        import stat
        def on_rm_error(func, p, exc_info):
            try:
                os.chmod(p, stat.S_IWRITE)
                func(p)
            except Exception:
                pass

        for p in req.paths:
            try:
                safe_path = await file_tools._resolve_safe_path(p, req.project_id)
                if safe_path.is_file():
                    safe_path.unlink(missing_ok=True)
                    deleted.append(p)
                elif safe_path.is_dir():
                    shutil.rmtree(str(safe_path), onerror=on_rm_error)
                    deleted.append(p)
            except Exception:
                pass
                
        await _broadcast_file_event("batch_delete", deleted, project_id=req.project_id, user=user)
        return {"status": "success", "deleted": deleted}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download_zip")
async def download_zip(
    paths: Optional[str] = Query(None, description="Comma-separated relative paths to include, or empty for all"),
    project_id: Optional[str] = Query(None, description="Project ID"),
    user: dict = Depends(require_auth)
):
    try:
        root = await file_tools.get_workspace_root(project_id)
        if not root.exists():
            raise HTTPException(status_code=404, detail="Workspace root not found.")

        target_paths = [p.strip() for p in paths.split(",") if p.strip()] if paths else []
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            if not target_paths:
                for dirpath, dirnames, filenames in os.walk(root):
                    dirnames[:] = [d for d in dirnames if d not in _TREE_IGNORE_DIRS and not d.startswith(".")]
                    for filename in filenames:
                        if filename.startswith("."):
                            continue
                        full = Path(dirpath) / filename
                        arcname = str(full.relative_to(root)).replace("\\", "/")
                        zf.write(full, arcname)
            else:
                for p in target_paths:
                    safe_path = await file_tools._resolve_safe_path(p, project_id)
                    if not safe_path.exists():
                        continue
                    if safe_path.is_file():
                        arcname = str(safe_path.relative_to(root)).replace("\\", "/")
                        zf.write(safe_path, arcname)
                    elif safe_path.is_dir():
                        for dirpath, dirnames, filenames in os.walk(safe_path):
                            dirnames[:] = [d for d in dirnames if d not in _TREE_IGNORE_DIRS and not d.startswith(".")]
                            for filename in filenames:
                                full = Path(dirpath) / filename
                                arcname = str(full.relative_to(root)).replace("\\", "/")
                                zf.write(full, arcname)

        zip_buffer.seek(0)
        filename = f"workspace_{project_id or 'export'}.zip"
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
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
            import stat
            def on_rm_error(func, p, exc_info):
                try:
                    os.chmod(p, stat.S_IWRITE)
                    func(p)
                except Exception:
                    pass

            shutil.rmtree(safe_path, onerror=on_rm_error)
            res = f"Success: Deleted directory '{path}'."
        else:
            raise HTTPException(status_code=404, detail="Path not found.")
            
        await _broadcast_file_event("delete", [path], project_id=project_id, user=user)
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
            .outerjoin(Message, Message.id == FileBackup.message_id)
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


# ============================================================
# File Version History API (Wave 2.3)
# ============================================================

@router.get("/history")
async def list_file_history(
    path: str = Query(..., description="Relative file path"),
    project_id: str | None = Query(None),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """List backup snapshots for a specific file path.

    Returns entries in reverse-chronological order (newest first).
    Each entry has enough metadata to render a history list in the UI.
    """
    from core.memory.models import FileBackup
    from sqlalchemy import select
    import pathlib

    # Resolve the absolute path for this relative path + project
    root = await file_tools.get_workspace_root(project_id)
    abs_path = str((root / path).resolve()).replace("\\", "/").lower()
    norm_rel = path.replace("\\", "/").strip("/").lower()
    filename = pathlib.Path(path).name.lower()

    stmt = (
        select(FileBackup)
        .where(
            FileBackup.file_path.ilike(f"%{filename}")
        )
        .order_by(FileBackup.created_at.desc())
        .limit(100)
    )
    result = await db.execute(stmt)
    backups = result.scalars().all()

    # Fine-grained match: prefer exact path match, then relative-path suffix, then filename
    filtered = [
        b for b in backups
        if b.file_path and (
            b.file_path.replace("\\", "/").lower() == abs_path
            or b.file_path.replace("\\", "/").lower().endswith("/" + norm_rel)
            or pathlib.Path(b.file_path).name.lower() == filename
        )
    ]

    return [
        {
            "id": str(b.id),
            "file_path": b.file_path,
            "operation": b.operation,
            "backup_file_name": b.backup_file_name,
            "created_at": b.created_at.isoformat() + "Z" if b.created_at else None,
            "has_content": bool(b.backup_file_name),
        }
        for b in filtered
    ]


@router.get("/history/content/{backup_id}")
async def get_backup_content(
    backup_id: str,
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Return the original content of a specific backup snapshot."""
    if not _valid_uuid(backup_id):
        raise HTTPException(status_code=400, detail="Invalid backup id")

    from core.memory.models import FileBackup
    from sqlalchemy import select
    import uuid

    result = await db.execute(select(FileBackup).where(FileBackup.id == uuid.UUID(backup_id)))
    backup = result.scalar_one_or_none()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    if not backup.backup_file_name:
        return {"content": "", "note": "No backup file recorded for this entry (create operation)."}

    team_carole_dir = await file_tools.get_team_carole_dir(str(backup.team_id))
    history_dir = team_carole_dir / "file-history"
    backup_path = history_dir / backup.backup_file_name

    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup file not found on disk")

    try:
        content = backup_path.read_text(encoding="utf-8")
        return {"content": content, "backup_id": backup_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read backup: {e}")


@router.post("/history/restore/{backup_id}")
async def restore_backup(
    backup_id: str,
    project_id: str | None = Query(None),
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Restore a file to a backup snapshot.

    Copies the backup file back to the live file path, effectively reverting
    the file to its pre-change state. The current file is overwritten.
    """
    if not _valid_uuid(backup_id):
        raise HTTPException(status_code=400, detail="Invalid backup id")

    from core.memory.models import FileBackup
    from sqlalchemy import select
    import uuid
    import shutil

    result = await db.execute(select(FileBackup).where(FileBackup.id == uuid.UUID(backup_id)))
    backup = result.scalar_one_or_none()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    if not backup.backup_file_name:
        raise HTTPException(status_code=400, detail="No backup content available for this entry")

    team_carole_dir = await file_tools.get_team_carole_dir(str(backup.team_id))
    history_dir = team_carole_dir / "file-history"
    backup_path = history_dir / backup.backup_file_name

    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup file not found on disk")

    target_path = backup.file_path

    # Sandbox check: ensure the restore destination is within the workspace
    from core.tools.file_tools import file_tools as _ft
    workspace_root = await _ft.get_workspace_root(project_id) if project_id else await _ft.get_workspace_root_for_team(str(backup.team_id))
    try:
        if os.name == "nt":
            Path(str(target_path).lower()).resolve().relative_to(Path(str(workspace_root).lower()).resolve())
        else:
            Path(target_path).resolve().relative_to(workspace_root.resolve())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Restore target path is outside the allowed workspace. Refusing to overwrite."
        )

    try:
        shutil.copy2(str(backup_path), target_path)
        norm_t = str(Path(target_path).resolve())
        for s in _ft._read_state.values():
            s.pop(norm_t, None)
        return {"status": "success", "message": f"Restored '{target_path}' from backup."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {e}")
