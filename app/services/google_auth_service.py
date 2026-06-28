from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from google.auth.transport import requests
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.logger import get_logger
from app.models.user import User
from app.schemas.auth import AccessTokenResponse, UserResponse
from app.services.auth_session_service import AuthSessionService, DeviceSessionContext

logger = get_logger(__name__)


class GoogleAuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    def build_authorization_url(self) -> tuple[str, str]:
        state = secrets.token_urlsafe(32)

        query_params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }

        return f"{settings.GOOGLE_AUTH_URL}?{urlencode(query_params)}", state

    async def exchange_code_for_tokens(self, code: str) -> dict:
        payload = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(settings.GOOGLE_TOKEN_URL, data=payload)

            if response.status_code != status.HTTP_200_OK:
                logger.warning("Google token exchange failed: %s", response.text)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unable to authenticate with Google",
                )

            return response.json()

        except httpx.TimeoutException as exc:
            logger.exception("Google token exchange timed out.")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Google authentication timed out",
            ) from exc

        except httpx.HTTPError as exc:
            logger.exception("Google token exchange failed due to HTTP error.")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Unable to reach Google authentication service",
            ) from exc

    def verify_google_id_token(self, raw_id_token: str) -> dict:
        try:
            payload = id_token.verify_oauth2_token(
                raw_id_token,
                requests.Request(),
                settings.GOOGLE_CLIENT_ID,
            )

            google_sub = payload.get("sub")
            email = payload.get("email")
            email_verified = payload.get("email_verified")

            if not google_sub:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Google account identifier not found",
                )

            if not email:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Google account email not found",
                )

            if not email_verified:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Google account email is not verified",
                )

            return payload

        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Invalid Google ID token.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google authentication token",
            ) from exc

    async def login_or_create_user(
        self,
        google_payload: dict,
        device_context: DeviceSessionContext,
    ) -> AccessTokenResponse:
        google_sub = google_payload["sub"]
        email = google_payload["email"].lower()
        full_name = google_payload.get("name") or email.split("@")[0]
        picture = google_payload.get("picture")

        try:
            user = await self.session.scalar(
                select(User).where(User.google_sub == google_sub)
            )

            if user is None:
                user = await self.session.scalar(
                    select(User).where(User.email == email)
                )

            if user is None:
                user = User(
                    full_name=full_name,
                    email=email,
                    password_hash=None,
                    auth_provider="google",
                    google_sub=google_sub,
                    profile_picture_url=picture,
                    email_verified=True,
                    role="user",
                    is_active=True,
                )
                self.session.add(user)
                await self.session.commit()
                await self.session.refresh(user)

                logger.info("Created new Google user '%s'.", user.id)

            else:
                if not user.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="User account is inactive",
                    )

                if user.google_sub and user.google_sub != google_sub:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This email is already linked with another Google account",
                    )

                user.google_sub = user.google_sub or google_sub
                user.profile_picture_url = picture
                user.email_verified = True

                await self.session.commit()
                await self.session.refresh(user)

                logger.info("Existing user logged in with Google '%s'.", user.id)

            (
                access_token,
                refresh_token,
                auth_session,
                expires_in,
                refresh_expires_in,
            ) = await AuthSessionService(self.session).issue_token_pair(
                user=user,
                device_context=device_context,
            )

            return AccessTokenResponse(
                access_token=access_token,
                expires_in=expires_in,
                expires_at=auth_session["expires_at"],
                refresh_token=refresh_token,
                refresh_token_expires_in=refresh_expires_in,
                refresh_token_expires_at=auth_session["refresh_expires_at"],
                user=UserResponse.model_validate(user),
                session=auth_session,
            )

        except HTTPException:
            raise
        except IntegrityError as exc:
            await self.session.rollback()
            logger.exception("Google login integrity conflict for '%s'.", email)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Unable to link Google account because this email already exists",
            ) from exc
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception("Database error during Google login for '%s'.", email)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to process Google login at the moment",
            ) from exc