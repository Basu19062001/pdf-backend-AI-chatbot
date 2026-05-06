from __future__ import annotations

from typing import Optional

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

_redis_client: Optional[Redis] = None


def get_redis_client() -> Optional[Redis]:
    """Return the shared Redis client when Redis support is enabled."""
    global _redis_client

    if not settings.REDIS_ENABLED:
        return None

    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_CONNECT_TIMEOUT,
        )

    return _redis_client


async def initialize_redis() -> None:
    """Initialize Redis connectivity if enabled, while tolerating fallback mode."""
    if not settings.REDIS_ENABLED:
        logger.info("Redis support is disabled. Authentication will use DB fallback only.")
        return

    client = get_redis_client()
    if client is None:
        logger.warning("Redis client could not be initialized. Using DB fallback only.")
        return

    try:
        await client.ping()
        logger.info("Redis connectivity initialized successfully.")
    except RedisError:
        logger.exception("Redis connectivity check failed. DB fallback will remain active.")


async def close_redis() -> None:
    """Close the shared Redis client during application shutdown."""
    global _redis_client

    if _redis_client is not None:
        await _redis_client.aclose()
        logger.info("Redis client closed.")
    _redis_client = None
