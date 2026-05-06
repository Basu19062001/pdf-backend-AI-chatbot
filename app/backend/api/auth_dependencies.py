from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db import get_db_session
from app.logger import get_logger
from app.models.user import User
from app.services.auth_service import AuthService

bearer_scheme = HTTPBearer(auto_error=False)
logger = get_logger(__name__)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
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
        user_id = uuid.UUID(payload["sub"])
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
        user = await AuthService(session).get_user_by_id(user_id)
        if user is None:
            logger.warning("Authenticated token references missing user '%s'.", user_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            logger.warning("Inactive user '%s' attempted authenticated access.", user_id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
            )
        logger.info("Authenticated request resolved for user '%s'.", user_id)
        return user
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error while loading authenticated user '%s'.", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to validate authentication credentials at the moment",
        ) from exc


CurrentUser = Annotated[User, Depends(get_current_user)]
