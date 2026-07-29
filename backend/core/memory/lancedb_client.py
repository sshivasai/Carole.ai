"""
# backend/core/memory/lancedb_client.py

Async-safe wrapper around the LanceDB vector store.

All LanceDB operations are synchronous (C-backed) and MUST be executed via
asyncio.to_thread() to avoid blocking the FastAPI event loop.
"""

import uuid
import asyncio
import logging
from typing import List, Optional, Dict, Any
from core.config import CAROLE_HOME_DIR

logger = logging.getLogger("carole.lancedb")

class LanceDBClient:
    def __init__(self, uri: str = None):
        if uri is None:
            self.uri = str(CAROLE_HOME_DIR / "vector_store")
        else:
            self.uri = uri
        self.table_name = "learnings"
        self._db = None  # lazy-initialise inside to_thread

    def _get_db(self):
        """Return (and lazily create) the LanceDB connection. Runs in a thread."""
        if self._db is None:
            import lancedb
            self._db = lancedb.connect(self.uri)
        return self._db

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def insert_learning(
        self,
        project_id: str,
        task_summary: str,
        lesson_rule: str,
        vector: List[float],
        team_id: Optional[str] = None,
    ) -> None:
        """Insert a new learning into the vector store (non-blocking)."""
        data = [{
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "team_id": team_id or "",
            "task_summary": task_summary,
            "lesson_rule": lesson_rule,
            "vector": vector,
        }]
        await asyncio.to_thread(self._sync_insert, data)

    async def search_learnings(
        self,
        vector: List[float],
        project_id: str,
        team_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search for similar learnings (non-blocking)."""
        return await asyncio.to_thread(
            self._sync_search, vector, project_id, team_id, limit
        )

    async def delete_learning(self, learning_id: str) -> bool:
        """Delete a learning record by id (non-blocking)."""
        return await asyncio.to_thread(self._sync_delete, learning_id)

    # ------------------------------------------------------------------
    # Private sync helpers (run inside to_thread)
    # ------------------------------------------------------------------

    def _sync_insert(self, data: List[dict]) -> None:
        try:
            db = self._get_db()
            if self.table_name in db.table_names():
                table = db.open_table(self.table_name)
                table.add(data)
            else:
                db.create_table(self.table_name, data=data)
        except Exception as e:
            logger.error("LanceDB insert failed: %s", e)
            raise

    def _sync_search(
        self,
        vector: List[float],
        project_id: str,
        team_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        try:
            db = self._get_db()
            if self.table_name not in db.table_names():
                return []

            table = db.open_table(self.table_name)

            # FIX H2: Sanitize IDs before embedding in the filter string.
            # LanceDB filter strings are SQL-like and not parameterized, so we
            # strip any character that isn't alphanumeric, a hyphen, or an
            # underscore.  Valid UUIDs only contain [0-9a-f-], so this is safe.
            import re as _re
            _safe_id = lambda s: _re.sub(r"[^a-zA-Z0-9_\-]", "", s) if s else ""
            safe_project_id = _safe_id(project_id)
            safe_team_id = _safe_id(team_id) if team_id else None

            # Match exact project AND (exact team OR project-wide learnings with empty team_id)
            filter_str = f"project_id = '{safe_project_id}'"
            if safe_team_id:
                filter_str += f" AND (team_id = '{safe_team_id}' OR team_id = '')"
            else:
                filter_str += " AND team_id = ''"

            results = (
                table.search(vector)
                .where(filter_str)
                .limit(limit)
                .to_list()
            )
            return results
        except Exception as e:
            logger.error("LanceDB search failed: %s", e)
            return []

    def _sync_delete(self, learning_id: str) -> bool:
        try:
            db = self._get_db()
            if self.table_name not in db.table_names():
                return False
            table = db.open_table(self.table_name)
            table.delete(f"id = '{learning_id}'")
            return True
        except Exception as e:
            logger.error("LanceDB delete failed: %s", e)
            return False


# Singleton
lancedb_client = LanceDBClient()
