"""Auth-only isolation. Run with --confcutdir=backend/auth_tests.

Never import main or the shared tests/conftest.py: both load unrelated services.
All application imports happen after disposable home/database configuration.
"""
import asyncio
import importlib.abc
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import pytest

BACKEND = Path(__file__).resolve().parents[1]
_sandbox = tempfile.TemporaryDirectory(prefix="carole-auth-tests-")
_home = Path(_sandbox.name)
_env = patch.dict(os.environ, {
    "HOME": str(_home),
    "USERPROFILE": str(_home),
    "DATABASE_URL": f"sqlite+aiosqlite:///{(_home / 'auth.db').as_posix()}",
    "JWT_SECRET": "isolated-auth-test-secret-not-for-production",
    "JWT_EXPIRY_HOURS": "72",
    "ENV": "test",
    "ENVIRONMENT": "test",
    "FORCE_DB_RECREATE": "false",
    "PYTHON_DOTENV_DISABLED": "1",
})
_env.start()
_home_patch = patch.object(Path, "home", return_value=_home)
_home_patch.start()
sys.path.insert(0, str(BACKEND))


class _NoApplicationStartup(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"main", "tests.conftest"}:
            raise AssertionError("Auth tests must not import app/shared fixtures")
        return None


_guard = _NoApplicationStartup()
sys.meta_path.insert(0, _guard)

from core.memory.database import Base, async_session, engine  # noqa: E402
from core.memory.models import User  # noqa: E402,F401
from core.auth.rate_limiter import limiter  # noqa: E402


@pytest.fixture(autouse=True)
async def isolated_database():
    assert Path(engine.url.database).parent == _home
    assert Path.home() == _home
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if limiter:
        limiter.reset()
        limiter.enabled = False
    yield
    if limiter:
        limiter.reset()
        limiter.enabled = False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db():
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client():
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from core.api.auth_routes import router
    from core.auth.auth_middleware import require_auth, optional_auth
    from fastapi import Depends
    from slowapi import _rate_limit_exceeded_handler
    from core.auth.rate_limiter import RateLimitExceeded

    app = FastAPI()
    app.include_router(router)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.get("/protected")
    async def protected(user=Depends(require_auth)):
        return user

    @app.get("/optional")
    async def optional(user=Depends(optional_auth)):
        return user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def pytest_sessionfinish(session, exitstatus):
    asyncio.run(engine.dispose())
    if limiter:
        limiter.reset()
        timer = getattr(limiter._storage, "timer", None)
        if timer:
            timer.cancel()
            timer.join()
    sys.meta_path.remove(_guard)
    _home_patch.stop()
    _env.stop()
    sys.path.remove(str(BACKEND))
    _sandbox.cleanup()
