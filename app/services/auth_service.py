from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.logger import get_logger
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    SignupResponse,
    UserLoginRequest,
    UserResponse,
    UserSignupRequest,
)
from app.services.auth_session_service import AuthSessionService, DeviceSessionContext

logger = get_logger(__name__)


class AuthService:
    """Production-oriented authentication service backed by SQLAlchemy."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def signup(self, payload: UserSignupRequest) -> SignupResponse:
        """Create a new active user account after validating uniqueness."""
        normalized_email = payload.email.lower()
        try:
            existing_user = await self._get_user_by_email(normalized_email)
            if existing_user is not None:
                logger.warning("User signup conflict detected for email '%s'.", normalized_email)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email already exists",
                )

            user = User(
                full_name=payload.full_name,
                email=normalized_email,
                password_hash=hash_password(payload.password.get_secret_value()),
                role="user",
                is_active=True,
            )

            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)
        except IntegrityError as exc:
            await self.session.rollback()
            logger.warning("User signup conflicted for email '%s'.", normalized_email)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            ) from exc
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception("Database error while signing up user '%s'.", normalized_email)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to create user account at the moment",
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            await self.session.rollback()
            logger.exception("Unexpected error during signup for '%s'.", normalized_email)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to create user account at the moment",
            ) from exc

        logger.info("User account created for '%s'.", normalized_email)
        return SignupResponse(user=UserResponse.model_validate(user))

    async def login(
        self,
        payload: UserLoginRequest,
        device_context: DeviceSessionContext,
    ) -> AccessTokenResponse:
        """Authenticate a user and issue a short-lived access token."""
        normalized_email = payload.email.lower()
        try:
            user = await self._get_user_by_email(normalized_email)
            password = payload.password.get_secret_value()

            if user is None or not verify_password(password, user.password_hash):
                logger.warning("Failed login attempt for email '%s'.", normalized_email)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            if not user.is_active:
                logger.warning("Inactive account login attempt for user '%s'.", user.id)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User account is inactive",
                )

            token, auth_session, expires_in = await AuthSessionService(self.session).issue_access_token(
                user=user,
                device_context=device_context,
            )
            logger.info("User '%s' authenticated successfully.", user.id)
            return AccessTokenResponse(
                access_token=token,
                expires_in=expires_in,
                expires_at=auth_session.expires_at,
                user=UserResponse.model_validate(user),
                session=auth_session,
            )
        except HTTPException:
            raise
        except SQLAlchemyError as exc:
            logger.exception("Database error while logging in email '%s'.", normalized_email)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to process login at the moment",
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected error during login for '%s'.", normalized_email)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to process login at the moment",
            ) from exc

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        """Load a user by primary key."""
        try:
            return await self.session.scalar(select(User).where(User.id == user_id))
        except SQLAlchemyError as exc:
            logger.exception("Database error while loading user '%s'.", user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to load user information at the moment",
            ) from exc

    async def _get_user_by_email(self, email: str) -> User | None:
        statement: Select[tuple[User]] = select(User).where(User.email == email)
        return await self.session.scalar(statement)
