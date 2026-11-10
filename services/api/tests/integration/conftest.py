"""
Fixtures untuk integration tests.

Menggunakan SQLite in-memory agar tidak memerlukan PostgreSQL saat CI.
DATABASE_URL di-set ke sqlite sebelum import app, sehingga session.py
membuat engine SQLite, bukan PostgreSQL.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator

# ⚠ Set env vars SEBELUM import apapun dari app — session.py membuat engine
# di module-level menggunakan settings.database_url
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///./test.db")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-integration-tests")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
import app.db.models  # noqa: F401 — import semua models agar metadata terdaftar

# Buat engine SQLite untuk test (berbeda dari engine di session.py)
_test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
)
_TestSessionLocal = async_sessionmaker(
    _test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables() -> AsyncGenerator[None, None]:
    """Buat semua tabel di SQLite sebelum test."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _test_engine.dispose()


@pytest_asyncio.fixture()
async def client() -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient dengan DB SQLite in-memory."""
    from app.db.session import get_db
    from app.main import app

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    app.dependency_overrides.clear()
