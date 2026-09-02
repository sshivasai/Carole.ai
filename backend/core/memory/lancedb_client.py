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
        project_id: Optional[str],
        task_summary: str,
        lesson_rule: str,
        vector: List[float],
        team_id: Optional[str] = None,
        learning_id: Optional[str] = None,
    ) -> str:
        """Insert a new learning into the vector store (non-blocking).
        Uses learning_id if provided to correlate 1-to-1 with SQLite Learning.id.
        """
        row_id = str(learning_id) if learning_id else str(uuid.uuid4())
        data = [{
            "id": row_id,
            "project_id": project_id or "",
            "team_id": team_id or "",
            "task_summary": task_summary,
            "lesson_rule": lesson_rule,
            "vector": vector,
        }]
        await asyncio.to_thread(self._sync_insert, data)
        return row_id

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

    def _has_table(self, db) -> bool:
        try:
            if hasattr(db, "list_tables"):
                res = db.list_tables()
                tables = getattr(res, "tables", res)
                return self.table_name in tables
            return self.table_name in db.table_names()
        except Exception:
            return False

    def _sync_insert(self, data: List[dict]) -> None:
        try:
            db = self._get_db()
            if self._has_table(db):
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
            if not self._has_table(db):
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

            # Match (exact project OR global) AND (exact team OR project-wide learnings with empty team_id)
            filter_str = f"(project_id = '{safe_project_id}' OR project_id = '')"
            if safe_team_id:
                filter_str += f" AND (team_id = '{safe_team_id}' OR team_id = '')"
            else:
                filter_str += " AND team_id = ''"

            results = (
                table.search(vector)
                .metric("cosine")
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
            import re as _re
            safe_id = _re.sub(r"[^a-zA-Z0-9_\-]", "", learning_id) if learning_id else ""
            if not safe_id:
                return False
            db = self._get_db()
            if not self._has_table(db):
                return False
            table = db.open_table(self.table_name)
            table.delete(f"id = '{safe_id}'")
            return True
        except Exception as e:
            logger.error("LanceDB delete failed: %s", e)
            return False

    async def update_project_id(self, learning_id: str, new_project_id: Optional[str]) -> bool:
        """Update the project_id of an existing learning (non-blocking)."""
        return await asyncio.to_thread(self._sync_update_project_id, learning_id, new_project_id)

    def _sync_update_project_id(self, learning_id: str, new_project_id: Optional[str]) -> bool:
        try:
            db = self._get_db()
            if not self._has_table(db):
                return False
            table = db.open_table(self.table_name)
            
            import re as _re
            safe_id = _re.sub(r"[^a-zA-Z0-9_\-]", "", learning_id) if learning_id else ""
            if not safe_id: return False
            
            # LanceDB update syntax
            table.update(where=f"id = '{safe_id}'", values={"project_id": new_project_id or ""})
            return True
        except Exception as e:
            logger.error("LanceDB update failed: %s", e)
            return False
# Singleton
lancedb_client = LanceDBClient()
