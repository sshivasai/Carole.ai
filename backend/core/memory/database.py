"""
# backend/core/memory/database.py

This file manages the SQLite/PostgreSQL database connection and setup.

Responsibilities:
1. Connect to SQLite via SQLAlchemy/Aiosqlite (or PostgreSQL via asyncpg).
2. Provide dependency injection sessions for FastAPI routes and background workers.
3. Run schema bootstrapping and Alembic migrations during startup.
4. Support force-recreate for dev environments (drops and recreates all tables).
"""

import os
import logging
import asyncio
from typing import Optional, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from core.config import CAROLE_HOME_DIR

logger = logging.getLogger("carole.database")

# Read the database URL from environment and normalize SQLite driver
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    _db_path = CAROLE_HOME_DIR / "carole.db"
    DATABASE_URL = f"sqlite+aiosqlite:///{_db_path.as_posix()}"
elif DATABASE_URL.startswith("sqlite://"):
    # Async SQLAlchemy requires sqlite+aiosqlite:// driver scheme
    DATABASE_URL = "sqlite+aiosqlite://" + DATABASE_URL[len("sqlite://"):]

_is_sqlite = DATABASE_URL.startswith("sqlite")

# Create async database engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for debugging SQL queries
    future=True
)

# Enable WAL mode for SQLite — reduces lock contention between concurrent
# readers and the single writer. This is a no-op for PostgreSQL.
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


def _register_orm_models():
    """Import all ORM models to ensure they register on Base.metadata before schema creation."""
    import core.memory.models  # noqa: F401


def _run_alembic_upgrade(stamp_only: bool = False) -> None:
    """Run Alembic migrations to head synchronously in a worker thread."""
    from pathlib import Path
    from alembic.config import Config
    from alembic import command

    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"
    if not ini_path.exists():
        logger.warning("Alembic configuration not found at %s; skipping migration.", ini_path)
        return

    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

    if stamp_only:
        command.stamp(alembic_cfg, "head")
    else:
        command.upgrade(alembic_cfg, "head")
    logger.info("Database migrations completed successfully.")


def _schema_gaps(connection):
    from sqlalchemy import inspect
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    gaps = []
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            gaps.append(table.name)
            continue
        columns = {column["name"] for column in inspector.get_columns(table.name)}
        gaps.extend(f"{table.name}.{column.name}" for column in table.columns if column.name not in columns)
    return gaps


async def verify_and_copy_sqlite_table(
    conn,
    source_table: str,
    target_table: str,
    indexes: Optional[List[str]] = None,
) -> None:
    """
    Atomically copies matching columns from source_table to target_table in SQLite.
    Verifies that source and target columns match before executing copy.
    Preserves indexes and ensures atomic execution within the current transaction.
    """
    src_res = await conn.execute(text(f"PRAGMA table_info({source_table})"))
    src_cols = {row[1] for row in src_res.fetchall()}

    tgt_res = await conn.execute(text(f"PRAGMA table_info({target_table})"))
    tgt_cols = {row[1] for row in tgt_res.fetchall()}

    common_cols = [c for c in src_cols if c in tgt_cols]
    if not common_cols:
        raise ValueError(f"Cannot copy rows: no common columns between '{source_table}' and '{target_table}'")

    col_names = ", ".join(f'"{c}"' for c in common_cols)
    await conn.execute(text(f'INSERT INTO "{target_table}" ({col_names}) SELECT {col_names} FROM "{source_table}"'))

    if indexes:
        for idx_sql in indexes:
            await conn.execute(text(idx_sql))


# Database initialization function
async def init_db(force_recreate: bool = False):
    """
    Initialize the database schema.
    
    Args:
        force_recreate: If True, drops all existing tables and recreates them.
                        ONLY permitted in explicit development mode.
                        Set via FORCE_DB_RECREATE=true environment variable.
    """
    # Guard FORCE_DB_RECREATE: disabled outside explicit development mode
    env = os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).lower()
    is_dev = env in ("development", "dev", "local", "test", "testing")
    force_env = os.getenv("FORCE_DB_RECREATE", "").lower() in ("true", "1", "yes")

    if force_env or force_recreate:
        if is_dev:
            force_recreate = True
        else:
            logger.warning(
                "FORCE_DB_RECREATE requested but ignored: disabled outside explicit development mode (current env=%r)",
                env,
            )
            force_recreate = False
    else:
        force_recreate = False

    # 1. Dynamically import all ORM models to register with Base.metadata before creation
    _register_orm_models()

    from sqlalchemy import inspect
    async with engine.begin() as conn:
        existing_tables = await conn.run_sync(lambda connection: set(inspect(connection).get_table_names()))
        had_version = "alembic_version" in existing_tables
        # 2. Optionally drop all tables first (explicit dev mode only)
        if force_recreate:
            logger.warning("FORCE_DB_RECREATE enabled — dropping all tables...")
            await conn.run_sync(Base.metadata.drop_all)
        
        # 3. Create all tables (additive — won't modify existing columns)
        await conn.run_sync(Base.metadata.create_all)

        # 3b. Additive SQLite column check for existing local databases
        if _is_sqlite:
            try:
                res = await conn.execute(text("PRAGMA table_info(projects)"))
                existing_cols = {row[1] for row in res.fetchall()}
                if "custom_workspace_path" not in existing_cols:
                    await conn.execute(text("ALTER TABLE projects ADD COLUMN custom_workspace_path VARCHAR(1024)"))
                    logger.info("Added 'custom_workspace_path' column to projects table.")

                task_res = await conn.execute(text("PRAGMA table_info(tasks)"))
                existing_task_cols = {row[1] for row in task_res.fetchall()}
                if "depends_on" not in existing_task_cols:
                    await conn.execute(text("ALTER TABLE tasks ADD COLUMN depends_on JSON DEFAULT '[]'"))
                    logger.info("Added 'depends_on' column to tasks table.")
            except Exception as e:
                logger.debug("Column addition notice: %s", e)

    # Versioned databases must successfully upgrade. Never stamp a failed
    # migration as applied. Unversioned, fully matching schemas can be adopted.
    if had_version and not force_recreate:
        await asyncio.to_thread(_run_alembic_upgrade)
    else:
        if _is_sqlite:
            # Older local installs used create_all without an Alembic revision.
            # These nullable additions preserve every existing checkpoint/row.
            async with engine.begin() as conn:
                cols = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("compaction_events")})
                if "owner_agent_id" not in cols:
                    await conn.execute(text("ALTER TABLE compaction_events ADD COLUMN owner_agent_id VARCHAR(100)"))
                if "snapshot" not in cols:
                    await conn.execute(text("ALTER TABLE compaction_events ADD COLUMN snapshot JSON"))
        async with engine.connect() as conn:
            gaps = await conn.run_sync(_schema_gaps)
        if gaps:
            raise RuntimeError("Unversioned database needs an explicit migration; missing columns: " + ", ".join(gaps))
        await asyncio.to_thread(_run_alembic_upgrade, True)
    async with engine.connect() as conn:
        gaps = await conn.run_sync(_schema_gaps)
    if gaps:
        raise RuntimeError("Database schema is incomplete after migration: " + ", ".join(gaps))
