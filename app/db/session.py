from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _build_connect_args() -> dict[str, int]:
    return {"timeout": settings.DB_CONNECT_TIMEOUT}


def _safe_database_label() -> str:
    try:
        return make_url(settings.database_url).database or "<unknown>"
    except Exception:
        return "<unknown>"


def get_engine() -> AsyncEngine:
    """Return a singleton async engine configured for production workloads."""
    global _engine, _session_factory

    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.DB_ECHO,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=settings.DB_POOL_PRE_PING,
            connect_args=_build_connect_args(),
        )
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        logger.info("Database engine initialized for '%s'.", _safe_database_label())

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory

    if _session_factory is None:
        get_engine()

    if _session_factory is None:
        raise RuntimeError("Database session factory is not initialized")

    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an async SQLAlchemy session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


async def ping_database() -> None:
    """Validate database connectivity with a lightweight query."""
    engine = get_engine()
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    logger.info("Database connectivity check succeeded.")


async def initialize_database() -> None:
    """Initialize and validate database resources during application startup."""
    await ping_database()


async def close_database() -> None:
    """Dispose the shared engine during application shutdown."""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        logger.info("Database engine disposed.")

    _engine = None
    _session_factory = None
