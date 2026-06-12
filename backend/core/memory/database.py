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
from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

# Ensure .carole directory exists
os.makedirs(".carole", exist_ok=True)

# Read the database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "sqlite+aiosqlite:///.carole/carole.db"

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
        finally:
            await session.close()

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
        from . import models
        
        # 2. Optionally drop all tables first (dev convenience)
        if force_recreate:
            print("⚠️ [DB] FORCE_DB_RECREATE enabled — dropping all tables...")
            await conn.run_sync(Base.metadata.drop_all)
        
        # 3. Create all tables (additive — won't modify existing columns)
        await conn.run_sync(Base.metadata.create_all)
