from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db import get_db_session
from app.logger import get_logger
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.auth_session_service import AuthSessionService

bearer_scheme = HTTPBearer(auto_error=False)
logger = get_logger(__name__)


@dataclass(slots=True)
class AuthenticatedRequestContext:
    user: User
    session_id: uuid.UUID
    token_jti: str


async def get_current_auth_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthenticatedRequestContext:
    """Resolve the currently authenticated user from a bearer token."""
    try:
        if credentials is None or credentials.scheme.lower() != "bearer":
            logger.warning("Missing or invalid authorization scheme on authenticated endpoint.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication credentials were not provided",
                headers={"WWW-Authenticate": "Bearer"},
            )

        payload = decode_access_token(credentials.credentials)
        validated_session = await AuthSessionService(session).validate_access_token(
            token=credentials.credentials,
            payload=payload,
        )
    except (KeyError, ValueError) as exc:
        logger.warning("Invalid JWT subject encountered during authentication.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error while decoding authentication token.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to validate authentication credentials at the moment",
        ) from exc

    try:
        user = await AuthService(session).get_user_by_id(validated_session.user_id)
        if user is None:
            logger.warning("Authenticated token references missing user '%s'.", validated_session.user_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            logger.warning("Inactive user '%s' attempted authenticated access.", validated_session.user_id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
            )
        await AuthSessionService(session).touch_session(validated_session.session_id)
        logger.info("Authenticated request resolved for user '%s'.", validated_session.user_id)
        return AuthenticatedRequestContext(
            user=user,
            session_id=validated_session.session_id,
            token_jti=validated_session.token_jti,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error while loading authenticated user '%s'.", validated_session.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to validate authentication credentials at the moment",
        ) from exc


async def get_current_user(
    auth_context: Annotated[AuthenticatedRequestContext, Depends(get_current_auth_context)],
) -> User:
    return auth_context.user


CurrentAuthContext = Annotated[AuthenticatedRequestContext, Depends(get_current_auth_context)]
CurrentUser = Annotated[User, Depends(get_current_user)]
