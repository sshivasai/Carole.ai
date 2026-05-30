"""
# backend/core/memory/database.py

This file manages the PostgreSQL database connection and setup, including pgvector for semantic memory.

Responsibilities:
1. Connect to PostgreSQL via SQLAlchemy/Asyncpg.
2. Initialize pgvector extension if it doesn't exist.
3. Provide dependency injection sessions for FastAPI routes and background workers.
4. Run schema bootstrapping during startup.
"""

import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

# Read the database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Fallback to local default if env variable is missing
    DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/charoledb"

# Create async database engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for debugging SQL queries
    future=True
)

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

# Database initialization function (creates pgvector extension & tables)
async def init_db():
    async with engine.begin() as conn:
        # 1. Enable the pgvector extension in PostgreSQL
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        
        # 2. Dynamically import models to register with Base metadata
        from . import models
        
        # 3. Create all tables
        await conn.run_sync(Base.metadata.create_all)
