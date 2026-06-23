"""
# backend/core/memory/scratchpad.py

ScratchpadStore — the single source of truth for agent scratchpads.

A scratchpad is a per-agent (or shared team) notepad that agents use to keep
partial plans, breadcrumbs, and cross-session notes.  Each team gets a directory
under its workspace:

    ~/.carole/workspaces/{project_slug}/{team_slug}/scratchpads/
        TEAM_NOTES.md            <- shared / common pad
        {Agent_Name}.md          <- one personal pad per agent

This module consolidates logic that was previously duplicated across
`tool_executor.py` (read/write wrappers) and `crud_routes.py` (REST endpoints),
adds the missing **update** (full replace) and **delete** (clear) operations,
**lists** every pad for a team (so the UI can show empty pads too), and
broadcasts a `scratchpad_updated` event on the EventBus so the frontend updates
in real time.

Design notes:
- Path resolution mirrors `file_tools.get_workspace_root` (slug rule + graceful
  fallback to raw ids when a Team/Project row is missing), but scopes pads one
  level deeper under the team slug.
- All mutations are serialized per-pad with an `asyncio.Lock` so concurrent
  agents cannot produce torn writes.
- IO is async via `aiofiles`.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from core.config import CAROLE_HOME_DIR
from core.chat.event_bus import event_bus

logger = logging.getLogger("carole.scratchpad")

# Team shared pad filename (everything else is "{Agent_Name}.md").
TEAM_PAD_FILENAME = "TEAM_NOTES.md"

_slug_cache: Dict[str, Dict[str, str]] = {}  # team_id -> {"project_slug", "team_slug"}


def _slugify(name: str) -> str:
    """Same slug rule used by `file_tools.get_workspace_root`."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name or "").strip("-")
    return slug


def _safe_agent_name(agent_name: str) -> str:
    """Filesystem-safe agent name (matches the legacy sanitisation rule)."""
    return (agent_name or "agent").replace(" ", "_").replace("/", "_")


class ScratchpadStore:
    """File-backed scratchpad store with realtime broadcast."""

    def __init__(self, base_dir: Optional[Path] = None):
        # `base_dir` is the *carole home* equivalent; scratchpads always live
        # under `<base_dir>/workspaces/...` to match `file_tools` conventions.
        self._base_dir = base_dir or CAROLE_HOME_DIR
        self._locks: Dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    # ------------------------------------------------------------------ paths

    @property
    def workspaces_dir(self) -> Path:
        return self._base_dir / "workspaces"

    async def _resolve_slugs(self, team_id: str) -> Dict[str, str]:
        """Resolve a team_id to {project_slug, team_slug} via the DB.

        Falls back to the raw id string when the row is missing or the id is not
        a valid UUID — mirroring `file_tools.get_workspace_root`'s fallbacks so
        scratchpads keep working even before a team is persisted.
        """
        cached = _slug_cache.get(team_id)
        if cached:
            return cached

        project_slug = team_id
        team_slug = team_id

        try:
            import uuid as _uuid
            from sqlalchemy import select
            from core.memory.database import async_session
            from core.memory.models import Team, Project

            team_uuid = _uuid.UUID(team_id)
            async with async_session() as db:
                team = (await db.execute(select(Team).where(Team.id == team_uuid))).scalar_one_or_none()
                if team:
                    team_slug = _slugify(team.name) or str(team.id)[:8]
                    project = (
                        await db.execute(select(Project).where(Project.id == team.project_id))
                    ).scalar_one_or_none()
                    if project:
                        project_slug = _slugify(project.name) or str(project.id)[:8]
                    else:
                        project_slug = str(team.project_id)
        except Exception as e:  # malformed uuid / db unavailable -> raw id fallback
            logger.debug("scratchpad slug fallback for team %s: %s", team_id, e)

        resolved = {"project_slug": project_slug, "team_slug": team_slug}
        _slug_cache[team_id] = resolved
        return resolved

    async def _team_dir(self, team_id: str) -> Path:
        slugs = await self._resolve_slugs(team_id)
        path = self.workspaces_dir / slugs["project_slug"] / slugs["team_slug"] / "scratchpads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def _pad_path(self, team_id: str, target: str, agent_name: str) -> Path:
        base = await self._team_dir(team_id)
        if target == "team":
            return base / TEAM_PAD_FILENAME
        return base / f"{_safe_agent_name(agent_name)}.md"

    async def _lock_for(self, path: Path) -> asyncio.Lock:
        key = str(path)
        async with self._locks_guard:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _label(target: str, agent_name: str) -> str:
        return "Team Scratchpad" if target == "team" else f"{agent_name or 'Agent'}'s Scratchpad"

    async def _read_file(self, path: Path) -> str:
        if not path.exists():
            return ""
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            return await f.read()

    async def _broadcast(
        self,
        team_id: str,
        target: str,
        agent_name: str,
        agent_id: str,
        content: str,
        action: str,
    ) -> None:
        """Push a realtime update to every connected client in the team."""
        try:
            await event_bus.publish(
                f"team:{team_id}",
                {
                    "type": "scratchpad_updated",
                    "action": action,  # write | update | delete
                    "target": target,
                    "agent_name": agent_name,
                    "agent_id": agent_id,
                    "content": content,
                    "label": self._label(target, agent_name),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as e:
            logger.warning("scratchpad broadcast failed: %s", e)

    def _entry(
        self, target: str, agent_name: str, agent_id: str, content: str, path: Path
    ) -> Dict[str, Any]:
        stat = path.stat() if path.exists() else None
        return {
            "target": target,
            "agent_name": agent_name,
            "agent_id": agent_id,
            "label": self._label(target, agent_name),
            "content": content,
            "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if stat else None,
            "size_bytes": stat.st_size if stat else 0,
        }

    # ------------------------------------------------------------------ public API

    async def list_pads(self, team_id: str, agents: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Return the team pad plus one entry per known agent (empty pads included)."""
        base = await self._team_dir(team_id)

        # 1. Team / common pad
        team_path = base / TEAM_PAD_FILENAME
        pads: List[Dict[str, Any]] = [
            self._entry("team", "Team", "", await self._read_file(team_path), team_path)
        ]

        # 2. One personal pad per agent in the roster
        seen_agents: set[str] = set()
        for a in agents or []:
            name = a.get("name") or a.get("agent_name") or "agent"
            aid = str(a.get("id") or a.get("agent_id") or "")
            seen_agents.add(_safe_agent_name(name))
            path = base / f"{_safe_agent_name(name)}.md"
            pads.append(self._entry("personal", name, aid, await self._read_file(path), path))

        # 3. Any stray pad files on disk whose agent is no longer in the roster
        try:
            for f in base.glob("*.md"):
                if f.name == TEAM_PAD_FILENAME:
                    continue
                if f.stem in seen_agents:
                    continue
                pads.append(self._entry("personal", f.stem, "", await self._read_file(f), f))
        except Exception as e:
            logger.debug("scratchpad glob failed: %s", e)

        return pads

    async def read(self, team_id: str, target: str, agent_name: str) -> Dict[str, Any]:
        path = await self._pad_path(team_id, target, agent_name)
        content = await self._read_file(path)
        return self._entry(target, agent_name, "", content, path)

    async def write(
        self,
        team_id: str,
        target: str,
        agent_name: str,
        content: str,
        mode: str = "append",
        agent_id: str = "",
        author: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append (default) or overwrite a pad. Append stamps an author/timestamp header.

        `agent_name` selects *which* pad is written; `author` (defaults to
        `agent_name`) is the name stamped in the append header — useful when a
        human edits an agent's personal pad.
        """
        if not content:
            return {"status": "error", "error": "content is required"}

        header_author = author or agent_name
        path = await self._pad_path(team_id, target, agent_name)
        lock = await self._lock_for(path)
        async with lock:
            if mode == "overwrite":
                async with aiofiles.open(path, "w", encoding="utf-8") as f:
                    await f.write(content)
            else:
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                async with aiofiles.open(path, "a", encoding="utf-8") as f:
                    await f.write(f"\n<!-- {header_author} @ {ts} -->\n{content}\n")

        updated = await self.read(team_id, target, agent_name)
        await self._broadcast(team_id, target, agent_name, agent_id, updated["content"], "write")
        return {"status": "ok", **updated}

    async def update(
        self,
        team_id: str,
        target: str,
        agent_name: str,
        content: str,
        agent_id: str = "",
        author: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Full replace (the 'update' CRUD). Equivalent to write(mode='overwrite')."""
        return await self.write(team_id, target, agent_name, content, mode="overwrite", agent_id=agent_id, author=author)

    async def delete(
        self,
        team_id: str,
        target: str,
        agent_name: str,
        agent_id: str = "",
    ) -> Dict[str, Any]:
        """Clear/remove a pad file (the 'delete' CRUD)."""
        path = await self._pad_path(team_id, target, agent_name)
        lock = await self._lock_for(path)
        async with lock:
            try:
                path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("scratchpad delete failed for %s: %s", path, e)

        await self._broadcast(team_id, target, agent_name, agent_id, "", "delete")
        return {"status": "ok", "label": self._label(target, agent_name), "deleted": True}


# Global singleton
scratchpad_store = ScratchpadStore()
