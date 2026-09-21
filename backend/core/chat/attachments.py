"""Validate attachment references before persisting or exposing them to a model."""
from pathlib import Path
from core.tools.file_tools import file_tools


async def normalize_chat_attachments(attachments, team_id: str, project_id: str):
    if not attachments:
        return []
    if not isinstance(attachments, list) or len(attachments) > 16:
        raise ValueError("At most 16 attachments are allowed")
    media_dir = (await file_tools.get_team_carole_dir(team_id) / "Chat_Media").resolve()
    clean = []
    for item in attachments:
        if not isinstance(item, dict):
            raise ValueError("Invalid attachment")
        kind = str(item.get("type", ""))[:100]
        if kind == "file_ref":
            path = str(item.get("path") or item.get("relative_path") or "")
            await file_tools._resolve_safe_path(path, project_id)
            clean.append({"type": kind, "path": path})
        elif item.get("local_path"):
            path = Path(str(item["local_path"])).resolve()
            if not path.is_relative_to(media_dir) or not path.is_file():
                raise ValueError("Attachment must be an uploaded file in this team")
            if path.stat().st_size > 50 * 1024 * 1024:
                raise ValueError("Attachment exceeds size limit")
            # URLs and local paths are generated from the validated storage entry.
            url = f"/api/media/{project_id}/{team_id}/{path.name}"
            clean.append({"type": kind, "name": str(item.get("name", path.name))[:255],
                          "local_path": str(path), "url": url})
        elif item.get("content"):
            clean.append({"type": "text/plain", "name": str(item.get("name", "attachment"))[:255],
                          "content": str(item["content"])[:8000]})
        else:
            raise ValueError("Attachment has no valid upload or file reference")
    return clean
