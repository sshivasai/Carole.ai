"""
# backend/tests/conftest.py

Shared pytest fixtures for testing the Carole.ai API.
Configures an in-memory SQLite database using aiosqlite for speed and isolation,
overriding the get_db dependency in FastAPI app.
"""

import os
import tempfile
from pathlib import Path
import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient, ASGITransport

_test_data = None
if os.environ.get("ENV") != "test" or not os.environ.get("CAROLE_HOME_DIR"):
    _test_data = tempfile.TemporaryDirectory(prefix="carole-pytest-")
    os.environ["CAROLE_HOME_DIR"] = str(Path(_test_data.name) / ".carole")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(Path(_test_data.name) / 'tests.db').as_posix()}"
    os.environ["ENV"] = "test"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from main import app
from core.memory.database import get_db, Base, engine as test_engine, async_session as TestSession
from core.auth.rate_limiter import limiter, SLOWAPI_AVAILABLE

from sqlalchemy.pool import StaticPool

if SLOWAPI_AVAILABLE and limiter:
    limiter.enabled = False

# Test SQLite in-memory database URL
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# Routes and services use the same disposable database. Merely overriding the
# HTTP dependency leaves background workers writing to a different database.


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    """Initializes the database schema and tool registry before tests run."""
    import core.memory.models  # Ensure all SQLAlchemy models are registered on Base.metadata
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
    if _test_data is not None:
        _test_data.cleanup()


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


@pytest.fixture
async def owned_browser(client):
    """Real authenticated ownership chain for browser HTTP/WebSocket regressions."""
    import uuid
    signup = await client.post("/api/auth/signup", json={"email": f"{uuid.uuid4()}@example.com", "password": "BrowserTest123!"})
    assert signup.status_code == 200, signup.text
    account = signup.json()
    headers = {"Authorization": "Bearer " + account["token"]}
    project = (await client.post("/api/projects", json={"name": "Browser fixture"}, headers=headers)).json()
    team = (await client.post("/api/teams", json={"name": "Browser team", "project_id": project["id"]}, headers=headers)).json()
    agent = (await client.post("/api/agents", json={"name": "Browser agent", "role": "developer", "team_id": team["id"], "model": "openrouter/free"}, headers=headers)).json()
    return {"headers": headers, "agent_id": agent["id"], "user_id": account["user"]["id"]}
