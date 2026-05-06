from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.api.auth_dependencies import CurrentAuthContext
from app.db import get_db_session
from app.logger import get_logger
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    AuthSessionListResponse,
    LogoutResponse,
    SignupResponse,
    UserLoginRequest,
    UserResponse,
    UserSignupRequest,
)
from app.services.auth_service import AuthService
from app.services.auth_session_service import AuthSessionService, DeviceSessionContext

router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    description=(
        "Create a new active user account with a securely hashed password. "
        "Email addresses are normalized to lowercase and must be unique."
    ),
)
async def signup(
    payload: UserSignupRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SignupResponse:
    """
    Register a new user account.

    This endpoint accepts the public signup payload, validates the submitted
    fields, normalizes the email address, hashes the incoming password, and
    persists a new active `User` record in the database.

    Args:
        payload: Incoming signup request containing full name, email, and password.
        session: Async database session injected by FastAPI.

    Returns:
        A signup response containing the created user's safe public profile.

    Raises:
        HTTPException: Returned when the email already exists or an unexpected
            server-side error prevents account creation.
    """
    try:
        response = await AuthService(session).signup(payload)
        logger.info("Signup endpoint completed successfully for '%s'.", payload.email.lower())
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled exception in signup endpoint for '%s'.", payload.email.lower())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create user account at the moment",
        ) from exc


@router.post(
    "/login",
    response_model=AccessTokenResponse,
    summary="Authenticate and issue a JWT access token",
    description=(
        "Validate user credentials and return a signed bearer token for subsequent "
        "authenticated requests."
    ),
)
async def login(
    request: Request,
    payload: UserLoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AccessTokenResponse:
    """
    Authenticate a user and issue a JWT bearer token.

    This endpoint validates the submitted credentials against the stored user
    record, verifies the password hash, checks whether the user account is
    active, and returns a signed access token for authenticated API access.

    Args:
        request: FastAPI request object used to capture device and network metadata.
        payload: Login request containing the user's email and password.
        session: Async database session injected by FastAPI.

    Returns:
        A bearer token response including the signed access token, expiry
        metadata, and the authenticated user's safe public profile.

    Raises:
        HTTPException: Returned when credentials are invalid, the account is
            inactive, or the authentication flow cannot be completed.
    """
    try:
        response = await AuthService(session).login(
            payload,
            _build_device_context(request, payload),
        )
        logger.info("Login endpoint completed for '%s'.", payload.email.lower())
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled exception in login endpoint for '%s'.", payload.email.lower())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process login at the moment",
        ) from exc


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the current authenticated user",
    description="Return the profile associated with the bearer token supplied in the request.",
)
async def get_me(auth_context: CurrentAuthContext) -> UserResponse:
    """
    Return the currently authenticated user's profile.

    This endpoint depends on bearer-token authentication. The incoming token is
    resolved by the auth dependency layer, which validates the token, loads the
    backing user record, and rejects missing, invalid, or inactive users before
    this handler is reached.

    Args:
        auth_context: The authenticated user and token-session context resolved from the access token.

    Returns:
        A safe user profile for the currently authenticated account.

    Raises:
        HTTPException: Returned when the profile cannot be serialized or an
            unexpected server-side error occurs.
    """
    try:
        user: User = auth_context.user
        logger.info("Profile fetched for authenticated user '%s'.", user.id)
        return UserResponse.model_validate(user)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled exception in current-user endpoint.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load authenticated user profile at the moment",
        ) from exc


@router.get(
    "/sessions",
    response_model=AuthSessionListResponse,
    summary="List active authenticated sessions",
    description=(
        "Return the currently authenticated user's active device sessions. "
        "Redis is used as the primary token store while the database remains the fallback source of truth."
    ),
)
async def list_sessions(
    auth_context: CurrentAuthContext,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthSessionListResponse:
    """
    List active device sessions for the authenticated user.

    This endpoint is useful for multi-device login management. Each returned
    item represents a persisted authenticated session, including device
    metadata, issuance time, and expiry time.

    Args:
        auth_context: Authenticated request context resolved from the bearer token.
        session: Async database session injected by FastAPI.

    Returns:
        A list of active sessions currently associated with the authenticated user.

    Raises:
        HTTPException: Returned when sessions cannot be loaded due to auth or
            server-side storage errors.
    """
    try:
        sessions = await AuthSessionService(session).list_user_sessions(auth_context.user.id)
        logger.info("Listed active auth sessions for user '%s'.", auth_context.user.id)
        return AuthSessionListResponse(items=sessions)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled exception while listing auth sessions.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load active sessions at the moment",
        ) from exc


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Delete the current authenticated session",
    description=(
        "Delete the currently authenticated access-token session from Redis and the database fallback store."
    ),
)
async def logout(
    auth_context: CurrentAuthContext,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LogoutResponse:
    """
    Delete the current authenticated session.

    This endpoint removes the active session from both Redis and the fallback
    database table so the current bearer token can no longer be used.

    Args:
        auth_context: Authenticated request context resolved from the bearer token.
        session: Async database session injected by FastAPI.

    Returns:
        A simple confirmation message after the active session has been removed.

    Raises:
        HTTPException: Returned when the session cannot be deleted or the
            caller is not authenticated.
    """
    try:
        await AuthSessionService(session).delete_session(
            session_id=auth_context.session_id,
            token_jti=auth_context.token_jti,
        )
        logger.info("Logged out auth session '%s' for user '%s'.", auth_context.session_id, auth_context.user.id)
        return LogoutResponse()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled exception while logging out current auth session.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete authenticated session at the moment",
        ) from exc


def _build_device_context(request: Request, payload: UserLoginRequest) -> DeviceSessionContext:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    forwarded_ip = forwarded_for.split(",")[0].strip() if forwarded_for else None
    client_ip = forwarded_ip or (request.client.host if request.client else None)

    return DeviceSessionContext(
        device_id=payload.device_id or request.headers.get("X-Device-Id"),
        device_name=payload.device_name or request.headers.get("X-Device-Name"),
        device_type=payload.device_type or request.headers.get("X-Device-Type") or "unknown",
        user_agent=request.headers.get("User-Agent"),
        ip_address=client_ip,
    )
