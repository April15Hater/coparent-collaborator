"""Shared pytest fixtures for coparent-collaborator tests.

Sets required environment variables before any app code is imported so that
config.py's startup validation does not call sys.exit(1).

Note: app/main.py has broken bare imports (e.g. `from routes_auth import`)
that don't match the actual file layout under app/routes/. We bypass main.py
entirely and assemble a test FastAPI app directly from the route modules.
"""

import os
import sys
from pathlib import Path

# Ensure the project root is in sys.path so `from app.* import` resolves.
sys.path.insert(0, str(Path(__file__).parent.parent))

# Must be set before importing any app module — config.py validates on import.
os.environ.setdefault("DEV_USER_EMAIL", "parenta@test.com")
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use")
os.environ.setdefault("SYNC_API_KEY", "test-sync-key")

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.auth as auth_module
import app.database as database_module
from app.models import Base, User
from app.routes.auth import router as auth_router
from app.routes.comments import router as comments_router
from app.routes.invite import router as invite_router
from app.routes.issues import router as issues_router
from app.routes.notifications import router as notifications_router

# ---------------------------------------------------------------------------
# In-memory SQLite engine — StaticPool keeps the same connection so the
# in-memory database is shared across requests within a single test.
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


def _build_test_app() -> FastAPI:
    """Build a fresh FastAPI app with all relevant routers included."""
    _app = FastAPI()
    _app.include_router(auth_router)
    _app.include_router(issues_router)
    _app.include_router(comments_router)
    _app.include_router(notifications_router)
    _app.include_router(invite_router)
    return _app


@pytest_asyncio.fixture
async def engine():
    """Per-test async SQLite engine with all tables created."""
    _engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    await _engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(session_factory):
    """Direct DB session for seeding test data."""
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def parent_a(db):
    user = User(email="parenta@test.com", display_name="Parent A", role="parent_a")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def parent_b(db):
    user = User(email="parentb@test.com", display_name="Parent B", role="parent_b")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# HTTP clients — each gets its own FastAPI app instance so dependency_overrides
# don't conflict when both client_a and client_b are used in the same test.
# ---------------------------------------------------------------------------


def _make_client(session_factory, current_user):
    """Return a context manager yielding an AsyncClient with DB+auth overridden."""
    _app = _build_test_app()

    async def override_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def override_user():
        return current_user

    _app.dependency_overrides[database_module.get_db] = override_db
    _app.dependency_overrides[auth_module.get_current_user] = override_user
    return AsyncClient(transport=ASGITransport(app=_app), base_url="http://test")


@pytest_asyncio.fixture
async def client_a(session_factory, parent_a):
    """Authenticated client acting as parent_a."""
    async with _make_client(session_factory, parent_a) as client:
        yield client


@pytest_asyncio.fixture
async def client_b(session_factory, parent_a, parent_b):
    """Authenticated client acting as parent_b (parent_a must also exist)."""
    async with _make_client(session_factory, parent_b) as client:
        yield client
