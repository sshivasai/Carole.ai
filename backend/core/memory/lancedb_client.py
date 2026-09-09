"""
# backend/core/memory/lancedb_client.py

Async-safe wrapper around the LanceDB vector store.

All LanceDB operations are synchronous (C-backed) and MUST be executed via
asyncio.to_thread() to avoid blocking the FastAPI event loop.
"""

import uuid
import asyncio
import logging
import threading
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
        self._write_lock = threading.RLock()

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
            "project_id": str(project_id) if project_id else "",
            "team_id": str(team_id) if team_id else "",
            "task_summary": task_summary,
            "lesson_rule": lesson_rule,
            "vector": list(vector),
            "embedding_model": getattr(vector, "model", "legacy"),
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
        candidates = await asyncio.to_thread(
            self._sync_search, vector, project_id, team_id, limit
        )
        # SQL is authoritative: stale/deleted vectors must never resurface, even
        # when an earlier indexing operation or a bulk delete was interrupted.
        from core.memory.database import async_session
        from core.memory.models import Learning
        from sqlalchemy import select, or_
        if not candidates:
            return []
        def as_uuid(value):
            return uuid.UUID(str(value)) if value else None
        ids = [as_uuid(row["id"]) for row in candidates]
        async with async_session() as db:
            stmt = select(Learning).where(Learning.id.in_(ids),
                Learning.project_id == as_uuid(project_id),
                or_(Learning.team_id == as_uuid(team_id), Learning.team_id.is_(None)))
            current = {str(row.id): row for row in (await db.scalars(stmt)).all()}
        return [row for row in candidates if row["id"] in current
                and row["task_summary"] == current[row["id"]].task_summary
                and row["lesson_rule"] == current[row["id"]].lesson_rule]

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
        with self._write_lock:
            self._sync_upsert(data)

    def _sync_upsert(self, data: List[dict]) -> None:
        try:
            db = self._get_db()
            if self._has_table(db):
                table = db.open_table(self.table_name)
                if "embedding_model" not in table.schema.names:
                    table.add_columns({"embedding_model": "'legacy'"})
                table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(data)
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
            _safe_id = lambda s: _re.sub(r"[^a-zA-Z0-9_\-]", "", str(s)) if s else ""
            safe_project_id = _safe_id(project_id)
            safe_team_id = _safe_id(team_id) if team_id else None

            # Match (exact project OR global) AND (exact team OR project-wide learnings with empty team_id)
            filter_str = f"project_id = '{safe_project_id}'"
            model = getattr(vector, "model", "legacy")
            if "embedding_model" in table.schema.names:
                filter_str += " AND embedding_model = '" + model.replace("'", "''") + "'"
            elif model != "legacy":
                return []
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
                return True
            table = db.open_table(self.table_name)
            table.delete(f"id = '{safe_id}'")
            return True
        except Exception as e:
            logger.error("LanceDB delete failed: %s", e)
            raise

    async def delete_by_team(self, team_id: str) -> bool:
        """Delete all learnings associated with a team (non-blocking)."""
        return await asyncio.to_thread(self._sync_delete_by_team, team_id)

    def _sync_delete_by_team(self, team_id: str) -> bool:
        try:
            import re as _re
            safe_id = _re.sub(r"[^a-zA-Z0-9_\-]", "", team_id) if team_id else ""
            if not safe_id:
                return False
            db = self._get_db()
            if not self._has_table(db):
                return False
            table = db.open_table(self.table_name)
            table.delete(f"team_id = '{safe_id}'")
            return True
        except Exception as e:
            logger.error("LanceDB delete_by_team failed: %s", e)
            return False

    async def delete_by_project(self, project_id: str) -> bool:
        """Delete all learnings associated with a project (non-blocking)."""
        return await asyncio.to_thread(self._sync_delete_by_project, project_id)

    def _sync_delete_by_project(self, project_id: str) -> bool:
        try:
            import re as _re
            safe_id = _re.sub(r"[^a-zA-Z0-9_\-]", "", project_id) if project_id else ""
            if not safe_id:
                return False
            db = self._get_db()
            if not self._has_table(db):
                return False
            table = db.open_table(self.table_name)
            table.delete(f"project_id = '{safe_id}'")
            return True
        except Exception as e:
            logger.error("LanceDB delete_by_project failed: %s", e)
            return False

    async def delete_learnings_batch(self, learning_ids: List[str]) -> bool:
        """Delete multiple learnings by ID (non-blocking)."""
        return await asyncio.to_thread(self._sync_delete_batch, learning_ids)

    def _sync_delete_batch(self, learning_ids: List[str]) -> bool:
        try:
            if not learning_ids:
                return True
            import re as _re
            safe_ids = [
                f"'{_re.sub(r'[^a-zA-Z0-9_\-]', '', lid)}'"
                for lid in learning_ids
                if lid and _re.sub(r'[^a-zA-Z0-9_\-]', '', lid)
            ]
            if not safe_ids:
                return False
            db = self._get_db()
            if not self._has_table(db):
                return False
            table = db.open_table(self.table_name)
            table.delete(f"id IN ({', '.join(safe_ids)})")
            return True
        except Exception as e:
            logger.error("LanceDB delete_batch failed: %s", e)
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
