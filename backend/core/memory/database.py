"""
# backend/core/memory/database.py

This file manages the SQLite database connection and setup.

Responsibilities:
1. Connect to SQLite via SQLAlchemy/Aiosqlite.
2. Provide dependency injection sessions for FastAPI routes and background workers.
3. Run schema bootstrapping during startup.
4. Support force-recreate for dev environments (drops and recreates all tables).
"""

import os
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from core.config import CAROLE_HOME_DIR

logger = logging.getLogger("carole.database")

# Read the database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    _db_path = CAROLE_HOME_DIR / "carole.db"
    DATABASE_URL = f"sqlite+aiosqlite:///{_db_path.as_posix()}"

_is_sqlite = DATABASE_URL.startswith("sqlite")

# Create async database engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for debugging SQL queries
    future=True
)

# Enable WAL mode for SQLite — reduces lock contention between concurrent
# readers and the single writer.  This is a no-op for PostgreSQL.
if _is_sqlite:
    from sqlalchemy import event as sa_event

    @sa_event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

# Async session factory
async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base class for models
Base = declarative_base()

# FastAPI Dependency Injection generator for DB sessions
async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

# Database initialization function
async def init_db(force_recreate: bool = False):
    """
    Initialize the database schema.
    
    Args:
        force_recreate: If True, drops all existing tables and recreates them.
                        Useful during development when schema changes are made.
                        Set via FORCE_DB_RECREATE=true environment variable.
    """
    # Check env var for force recreate
    if os.getenv("FORCE_DB_RECREATE", "").lower() in ("true", "1", "yes"):
        force_recreate = True

    async with engine.begin() as conn:
        # 1. Dynamically import models to register with Base metadata
        
        # 2. Optionally drop all tables first (dev convenience)
        if force_recreate:
            logger.warning("FORCE_DB_RECREATE enabled — dropping all tables...")
            await conn.run_sync(Base.metadata.drop_all)
        
        # 3. Create all tables (additive — won't modify existing columns)
        await conn.run_sync(Base.metadata.create_all)
        
        # 4. Additive migration — add missing columns if they don't exist yet
        # TODO: Replace this brittle ALTER TABLE approach with Alembic when
        #       the schema stabilises for production.
        if _is_sqlite:
            for query in [
                "ALTER TABLE messages ADD COLUMN reasoning_text TEXT",
                "ALTER TABLE file_backups ADD COLUMN backup_file_name VARCHAR(255)",
                "ALTER TABLE compaction_events ADD COLUMN covered_through_message_id VARCHAR(36)",
                "ALTER TABLE compaction_events ADD COLUMN covered_through_timestamp DATETIME",
            ]:
                try:
                    await conn.execute(text(query))
                except Exception as e:
                    # Duplicate column error is expected on existing databases
                    if "duplicate column name" not in str(e).lower():
                        logger.info("DB Migration Notice: %s", e)

        # 5. Fix file_backups.message_id NOT NULL constraint mismatch.
        #    The initial migration created this column as NOT NULL, but the
        #    SQLAlchemy model defines it as nullable=True. Subagents hit an
        #    IntegrityError on every write_file because they have no
        #    active_message_id at their first tool call.
        #    SQLite doesn't support ALTER COLUMN, so we use the recommended
        #    table-rebuild approach.
        if _is_sqlite:
            try:
                # Check current nullability via PRAGMA table_info
                result = await conn.execute(text("PRAGMA table_info(file_backups)"))
                rows = result.fetchall()
                col_info = {row[1]: row for row in rows}  # name -> row
                msg_id_col = col_info.get("message_id")
                # notnull=1 means it's NOT NULL — we need to make it nullable
                if msg_id_col and msg_id_col[3] == 1:
                    logger.info("DB Migration: Fixing file_backups.message_id NOT NULL → nullable...")
                    await conn.execute(text(
                        "CREATE TABLE IF NOT EXISTS file_backups_new ("
                        "  id TEXT NOT NULL, "
                        "  team_id TEXT NOT NULL, "
                        "  message_id TEXT NULL, "
                        "  file_path TEXT NOT NULL, "
                        "  backup_file_name VARCHAR(255), "
                        "  operation VARCHAR(20) NOT NULL DEFAULT 'write_file', "
                        "  created_at DATETIME, "
                        "  PRIMARY KEY (id), "
                        "  FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE, "
                        "  FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE"
                        ")"
                    ))
                    await conn.execute(text(
                        "INSERT INTO file_backups_new "
                        "SELECT id, team_id, message_id, file_path, backup_file_name, operation, created_at "
                        "FROM file_backups"
                    ))
                    await conn.execute(text("DROP TABLE file_backups"))
                    await conn.execute(text("ALTER TABLE file_backups_new RENAME TO file_backups"))
                    logger.info("DB Migration: file_backups.message_id is now nullable.")
            except Exception as e:
                logger.warning("DB Migration: Could not fix file_backups.message_id: %s", e)

