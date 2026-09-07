"""
# backend/tests/conftest.py

Shared pytest fixtures for testing the Carole.ai API.
Configures an in-memory SQLite database using aiosqlite for speed and isolation,
overriding the get_db dependency in FastAPI app.
"""

import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient, ASGITransport

from main import app
from core.memory.database import get_db, Base
from core.auth.rate_limiter import limiter, SLOWAPI_AVAILABLE

from sqlalchemy.pool import StaticPool

if SLOWAPI_AVAILABLE and limiter:
    limiter.enabled = False

# Test SQLite in-memory database URL
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# Create async engine for testing with StaticPool to keep single in-memory instance
test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False
)

# Async session factory
TestSession = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    """Initializes the database schema and tool registry before tests run."""
    from core.tools.tool_executor import register_builtin_tools
    register_builtin_tools()

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    # Dispose both the test engine and the production engine so aiosqlite's
    # non-daemon worker threads shut down; otherwise the interpreter hangs at
    # exit waiting to join them.
    await test_engine.dispose()
    from core.memory.database import engine as prod_engine
    await prod_engine.dispose()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides a clean database session for a single test."""
    async with TestSession() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provides a configured HTTPX AsyncClient for FastAPI test routes."""
    # Override get_db dependency to use the test session with commit on success
    async def override_get_db():
        async with TestSession() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    # Use ASGITransport to test ASGI app directly
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=True) as ac:
        yield ac

    app.dependency_overrides.clear()
