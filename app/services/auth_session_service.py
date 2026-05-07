from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy import delete, select
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis_client
from app.core.config import settings
from app.core.security import create_access_token, hash_token
from app.logger import get_logger
from app.models.user import User
from app.models.user_auth_session import UserAuthSession

logger = get_logger(__name__)
AUTH_SESSION_TABLE_NAME = "user_auth_sessions"


@dataclass(slots=True)
class DeviceSessionContext:
    device_id: str | None = None
    device_name: str | None = None
    device_type: str | None = None
    user_agent: str | None = None
    ip_address: str | None = None


@dataclass(slots=True)
class ValidatedAuthSession:
    user_id: uuid.UUID
    session_id: uuid.UUID
    token_jti: str


class AuthSessionService:
    """Manage one auth-session row per user with device/token entries stored as JSON."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def issue_access_token(
        self,
        user: User,
        device_context: DeviceSessionContext,
    ) -> tuple[str, dict[str, Any], int]:
        """Create a device-bound access token and return the public session payload."""
        await self.purge_expired_sessions()

        session_row = await self._get_or_create_user_session_row(user.id)
        session_id = uuid.uuid4()
        token_jti = uuid.uuid4().hex
        token, issued_at, expires_at = create_access_token(
            subject=str(user.id),
            session_id=session_id,
            token_jti=token_jti,
            additional_claims={"email": user.email, "role": user.role},
        )

        session_entry = self._build_session_entry(
            session_id=session_id,
            token_jti=token_jti,
            token=token,
            device_context=device_context,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        active_sessions = self._active_sessions(session_row.active_sessions)
        active_sessions.append(session_entry)
        session_row.active_sessions = active_sessions

        try:
            await self.session.commit()
            await self.session.refresh(session_row)
        except SQLAlchemyError as exc:
            await self.session.rollback()
            if self._is_missing_auth_session_table(exc):
                logger.warning(
                    "Auth session storage table '%s' is missing during login for user '%s'.",
                    AUTH_SESSION_TABLE_NAME,
                    user.id,
                )
                raise self._auth_session_table_missing_http_error() from exc
            logger.exception("Failed to persist aggregated auth sessions for user '%s'.", user.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to create an authenticated session at the moment",
            ) from exc

        expires_in = self._remaining_seconds(expires_at)
        await self._cache_session(user.id, session_entry, expires_in)
        logger.info(
            "Issued nested auth session '%s' for user '%s' on device '%s'.",
            session_entry["session_id"],
            user.id,
            session_entry["device_type"] or "unknown",
        )
        return token, self._public_session_view(session_entry), expires_in

    async def validate_access_token(
        self,
        token: str,
        payload: dict[str, str],
    ) -> ValidatedAuthSession:
        """Validate a signed access token against Redis and the aggregated DB session row."""
        token_jti = payload["jti"]
        session_id = uuid.UUID(payload["sid"])
        user_id = uuid.UUID(payload["sub"])
        token_digest = hash_token(token)

        cached_session = await self._get_cached_session(token_jti)
        if cached_session is not None:
            if (
                cached_session.get("token_hash") != token_digest
                or cached_session.get("session_id") != str(session_id)
                or cached_session.get("user_id") != str(user_id)
            ):
                logger.warning("Redis token validation mismatch for jti '%s'.", token_jti)
                await self._delete_cached_session(token_jti)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Could not validate authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return ValidatedAuthSession(user_id=user_id, session_id=session_id, token_jti=token_jti)

        session_row = await self._load_user_session_row(user_id)
        session_entry = self._find_session_entry(
            session_row.active_sessions if session_row else [],
            session_id=session_id,
            token_jti=token_jti,
        )
        if session_entry is None or session_entry.get("token_hash") != token_digest:
            logger.warning("DB fallback could not validate nested session '%s'.", session_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        expires_at = self._parse_dt(session_entry["expires_at"])
        if expires_at <= datetime.now(timezone.utc):
            logger.info("Expired nested auth session '%s' encountered during validation.", session_id)
            await self.delete_session(session_id=session_id, token_jti=token_jti, user_id=user_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        await self._cache_session(user_id, session_entry, self._remaining_seconds(expires_at))
        return ValidatedAuthSession(user_id=user_id, session_id=session_id, token_jti=token_jti)

    async def list_user_sessions(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return all active nested sessions for a user from the single aggregated row."""
        await self.purge_expired_sessions()
        try:
            session_row = await self.session.scalar(
                select(UserAuthSession).where(UserAuthSession.user_id == user_id)
            )
        except SQLAlchemyError as exc:
            if self._is_missing_auth_session_table(exc):
                logger.warning(
                    "Auth session storage table '%s' is missing while listing sessions for user '%s'.",
                    AUTH_SESSION_TABLE_NAME,
                    user_id,
                )
                raise self._auth_session_table_missing_http_error() from exc
            logger.exception("Failed to list auth sessions for user '%s'.", user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to load active sessions at the moment",
            ) from exc

        if session_row is None:
            return []

        sessions = self._sorted_sessions(self._active_sessions(session_row.active_sessions))
        return [self._public_session_view(entry) for entry in sessions]

    async def touch_session(self, session_id: uuid.UUID) -> None:
        """Update the nested last-seen timestamp for a specific device session."""
        now = datetime.now(timezone.utc)
        try:
            session_row = await self._load_session_row_by_nested_session_id(session_id)
            if session_row is None:
                return
            active_sessions = self._active_sessions(session_row.active_sessions)
            updated = False
            for entry in active_sessions:
                if entry.get("session_id") == str(session_id):
                    entry["last_seen_at"] = self._serialize_dt(now)
                    entry["updated_at"] = self._serialize_dt(now)
                    updated = True
                    break
            if not updated:
                return
            session_row.active_sessions = active_sessions
            await self.session.commit()
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Failed to update last_seen_at for nested auth session '%s'.", session_id)

    async def delete_session(
        self,
        session_id: uuid.UUID,
        token_jti: str,
        user_id: uuid.UUID | None = None,
    ) -> None:
        """Delete one nested session entry from the user's single auth-session row."""
        try:
            session_row = None
            if user_id is not None:
                session_row = await self.session.scalar(
                    select(UserAuthSession).where(UserAuthSession.user_id == user_id)
                )
            if session_row is None:
                session_row = await self._load_session_row_by_nested_session_id(session_id)
            if session_row is None:
                await self._delete_cached_session(token_jti)
                return

            active_sessions = [
                entry
                for entry in self._active_sessions(session_row.active_sessions)
                if entry.get("session_id") != str(session_id)
            ]
            if active_sessions:
                session_row.active_sessions = active_sessions
            else:
                await self.session.delete(session_row)
            await self.session.commit()
        except SQLAlchemyError as exc:
            await self.session.rollback()
            if self._is_missing_auth_session_table(exc):
                logger.warning(
                    "Auth session storage table '%s' is missing while deleting nested session '%s'.",
                    AUTH_SESSION_TABLE_NAME,
                    session_id,
                )
                raise self._auth_session_table_missing_http_error() from exc
            logger.exception("Failed to delete nested auth session '%s' from DB.", session_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to delete authenticated session at the moment",
            ) from exc

        await self._delete_cached_session(token_jti)
        logger.info("Deleted nested auth session '%s'.", session_id)

    async def purge_expired_sessions(self) -> int:
        """Remove expired nested sessions from aggregated user rows and delete empty rows."""
        now = datetime.now(timezone.utc)
        deleted_sessions = 0
        try:
            result = await self.session.scalars(select(UserAuthSession))
            session_rows = list(result.all())
            for session_row in session_rows:
                current_sessions = self._active_sessions(session_row.active_sessions)
                retained_sessions: list[dict[str, Any]] = []
                for entry in current_sessions:
                    expires_at = self._parse_dt(entry["expires_at"])
                    if expires_at <= now:
                        deleted_sessions += 1
                        token_jti = entry.get("token_jti")
                        if token_jti:
                            await self._delete_cached_session(token_jti)
                    else:
                        retained_sessions.append(entry)

                if retained_sessions != current_sessions:
                    if retained_sessions:
                        session_row.active_sessions = retained_sessions
                    else:
                        await self.session.delete(session_row)

            await self.session.commit()
            if deleted_sessions:
                logger.info("Purged %s expired nested auth sessions from the database.", deleted_sessions)
            return deleted_sessions
        except SQLAlchemyError as exc:
            await self.session.rollback()
            if self._is_missing_auth_session_table(exc):
                logger.warning(
                    "Auth session storage table '%s' is missing during expired-session purge. "
                    "Apply the auth session migrations before using auth sessions.",
                    AUTH_SESSION_TABLE_NAME,
                )
                return 0
            logger.exception("Failed to purge expired nested auth sessions.")
            return 0

    async def _get_or_create_user_session_row(self, user_id: uuid.UUID) -> UserAuthSession:
        session_row = await self._load_user_session_row(user_id)
        if session_row is not None:
            return session_row

        session_row = UserAuthSession(id=user_id, user_id=user_id, active_sessions=[])
        self.session.add(session_row)
        await self.session.flush()
        return session_row

    async def _load_user_session_row(self, user_id: uuid.UUID) -> UserAuthSession | None:
        try:
            return await self.session.scalar(
                select(UserAuthSession).where(UserAuthSession.user_id == user_id)
            )
        except SQLAlchemyError as exc:
            if self._is_missing_auth_session_table(exc):
                logger.warning(
                    "Auth session storage table '%s' is missing while loading user '%s' auth row.",
                    AUTH_SESSION_TABLE_NAME,
                    user_id,
                )
                raise self._auth_session_table_missing_http_error() from exc
            logger.exception("Failed to load aggregated auth-session row for user '%s'.", user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to validate authentication credentials at the moment",
            ) from exc

    async def _load_session_row_by_nested_session_id(
        self,
        session_id: uuid.UUID,
    ) -> UserAuthSession | None:
        try:
            result = await self.session.scalars(select(UserAuthSession))
            session_rows = list(result.all())
        except SQLAlchemyError as exc:
            if self._is_missing_auth_session_table(exc):
                logger.warning(
                    "Auth session storage table '%s' is missing while scanning for nested session '%s'.",
                    AUTH_SESSION_TABLE_NAME,
                    session_id,
                )
                raise self._auth_session_table_missing_http_error() from exc
            logger.exception("Failed to scan aggregated auth-session rows for nested session '%s'.", session_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to delete authenticated session at the moment",
            ) from exc

        for session_row in session_rows:
            for entry in self._active_sessions(session_row.active_sessions):
                if entry.get("session_id") == str(session_id):
                    return session_row
        return None

    def _build_session_entry(
        self,
        session_id: uuid.UUID,
        token_jti: str,
        token: str,
        device_context: DeviceSessionContext,
        issued_at: datetime,
        expires_at: datetime,
    ) -> dict[str, Any]:
        timestamp = self._serialize_dt(issued_at)
        expires_timestamp = self._serialize_dt(expires_at)
        return {
            "session_id": str(session_id),
            "token_jti": token_jti,
            "token_hash": hash_token(token),
            "device_id": device_context.device_id,
            "device_name": device_context.device_name,
            "device_type": device_context.device_type,
            "user_agent": device_context.user_agent,
            "ip_address": device_context.ip_address,
            "issued_at": timestamp,
            "expires_at": expires_timestamp,
            "last_seen_at": timestamp,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    async def _cache_session(self, user_id: uuid.UUID, session_entry: dict[str, Any], expires_in: int) -> None:
        client = get_redis_client()
        if client is None:
            return

        payload = json.dumps(
            {
                "session_id": session_entry["session_id"],
                "user_id": str(user_id),
                "token_jti": session_entry["token_jti"],
                "token_hash": session_entry["token_hash"],
                "expires_at": session_entry["expires_at"],
            }
        )
        try:
            await client.set(self._redis_key(session_entry["token_jti"]), payload, ex=max(1, expires_in))
        except RedisError:
            logger.exception("Failed to cache nested auth session '%s' in Redis.", session_entry["session_id"])

    async def _get_cached_session(self, token_jti: str) -> dict[str, str] | None:
        client = get_redis_client()
        if client is None:
            return None

        try:
            payload = await client.get(self._redis_key(token_jti))
        except RedisError:
            logger.exception("Failed to read auth session '%s' from Redis.", token_jti)
            return None

        if not payload:
            return None

        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Invalid Redis payload detected for auth session '%s'.", token_jti)
            await self._delete_cached_session(token_jti)
            return None

    async def _delete_cached_session(self, token_jti: str) -> None:
        client = get_redis_client()
        if client is None:
            return

        try:
            await client.delete(self._redis_key(token_jti))
        except RedisError:
            logger.exception("Failed to delete cached auth session '%s'.", token_jti)

    def _find_session_entry(
        self,
        active_sessions: list[dict[str, Any]],
        session_id: uuid.UUID,
        token_jti: str,
    ) -> dict[str, Any] | None:
        for entry in self._active_sessions(active_sessions):
            if entry.get("session_id") == str(session_id) and entry.get("token_jti") == token_jti:
                return entry
        return None

    def _active_sessions(self, active_sessions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if not active_sessions:
            return []
        return [dict(entry) for entry in active_sessions]

    def _sorted_sessions(self, active_sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            active_sessions,
            key=lambda entry: (
                self._parse_dt(entry["last_seen_at"]),
                self._parse_dt(entry["created_at"]),
            ),
            reverse=True,
        )

    def _public_session_view(self, entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": entry["session_id"],
            "device_id": entry.get("device_id"),
            "device_name": entry.get("device_name"),
            "device_type": entry.get("device_type"),
            "user_agent": entry.get("user_agent"),
            "ip_address": entry.get("ip_address"),
            "issued_at": entry["issued_at"],
            "expires_at": entry["expires_at"],
            "last_seen_at": entry["last_seen_at"],
            "created_at": entry["created_at"],
            "updated_at": entry["updated_at"],
        }

    def _serialize_dt(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    def _parse_dt(self, value: str) -> datetime:
        return datetime.fromisoformat(value)

    def _redis_key(self, token_jti: str) -> str:
        return f"{settings.REDIS_TOKEN_KEY_PREFIX}:{token_jti}"

    def _remaining_seconds(self, expires_at: datetime) -> int:
        return max(1, int((expires_at - datetime.now(timezone.utc)).total_seconds()))

    def _is_missing_auth_session_table(self, exc: SQLAlchemyError) -> bool:
        if not isinstance(exc, ProgrammingError):
            return False

        message = str(exc).lower()
        return AUTH_SESSION_TABLE_NAME in message and "does not exist" in message

    def _auth_session_table_missing_http_error(self) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Authentication session storage is not initialized. "
                "Run the latest database migrations and try again."
            ),
        )
