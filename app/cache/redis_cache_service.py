from __future__ import annotations

import json
from typing import Any

from redis.exceptions import RedisError

from app.cache.redis_client import get_redis_client
from app.core.config import settings
from app.logger import get_logger

logger = get_logger(__name__)


class RedisCacheService:
    """Reusable Redis helper with namespaced key building and common operations."""

    def __init__(self, namespace: str | None = None):
        self.namespace = namespace.strip(":") if namespace else None

    def build_key(self, *parts: object) -> str:
        key_parts = [settings.REDIS_KEY_PREFIX.strip(":")]
        if self.namespace:
            key_parts.append(self.namespace)
        key_parts.extend(str(part).strip(":") for part in parts if str(part).strip(":"))
        return ":".join(key_parts)

    async def set_value(self, value: str, *parts: object, expires_in: int | None = None) -> bool:
        client = get_redis_client()
        if client is None:
            logger.warning("Redis client unavailable. Skipping cache write for namespace '%s'.", self.namespace)
            return False

        key = self.build_key(*parts)
        try:
            await client.set(key, value, ex=expires_in)
        except RedisError:
            logger.exception("Failed to set Redis key '%s'.", key)
            return False
        logger.info("Stored value in Redis cache for key '%s' with ttl=%s.", key, expires_in)
        return True

    async def get_value(self, *parts: object) -> str | None:
        client = get_redis_client()
        if client is None:
            logger.warning("Redis client unavailable. Skipping cache read for namespace '%s'.", self.namespace)
            return None

        key = self.build_key(*parts)
        try:
            value = await client.get(key)
        except RedisError:
            logger.exception("Failed to read Redis key '%s'.", key)
            return None
        if value is None:
            logger.info("Redis cache miss for key '%s'.", key)
            return None
        logger.info("Redis cache hit for key '%s'.", key)
        return value

    async def delete(self, *parts: object) -> bool:
        client = get_redis_client()
        if client is None:
            logger.warning("Redis client unavailable. Skipping cache delete for namespace '%s'.", self.namespace)
            return False

        key = self.build_key(*parts)
        try:
            deleted = await client.delete(key)
        except RedisError:
            logger.exception("Failed to delete Redis key '%s'.", key)
            return False
        logger.info("Deleted Redis key '%s'. deleted=%s", key, bool(deleted))
        return True

    async def set_json(self, value: dict[str, Any], *parts: object, expires_in: int | None = None) -> bool:
        return await self.set_value(json.dumps(value), *parts, expires_in=expires_in)

    async def get_json(self, *parts: object) -> dict[str, Any] | None:
        payload = await self.get_value(*parts)
        if not payload:
            return None

        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            key = self.build_key(*parts)
            logger.warning("Invalid JSON payload detected for Redis key '%s'.", key)
            await self.delete(*parts)
            return None
