"""Async SQLAlchemy engine + session factory."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import settings


def _async_url(url: str) -> str:
    """Normalize managed-Postgres URLs (Railway/Heroku style) for asyncpg.

    They hand out postgres:// or postgresql:// and sometimes ?sslmode=require —
    asyncpg needs the +asyncpg driver marker and `ssl=` instead of `sslmode=`.
    """
    if not url.strip():
        raise RuntimeError(
            "DATABASE_URL is set but empty. On Railway this means the variable "
            "references a database service that doesn't exist — add a PostgreSQL "
            "service to the project and point DATABASE_URL at it "
            "(e.g. ${{Postgres.DATABASE_URL}}), or paste a full postgresql:// URL."
        )
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url.replace("sslmode=", "ssl=")


engine = create_async_engine(_async_url(settings.database_url), echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session, commits on success, rolls back on error."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create the pgvector extension and all tables on startup (idempotent)."""
    from sqlalchemy import text

    from . import models  # noqa: F401 — registers tables on Base.metadata

    async with engine.begin() as conn:
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception:
            # Non-pgvector Postgres or insufficient privs — vector cols degrade.
            pass
        await conn.run_sync(Base.metadata.create_all)
