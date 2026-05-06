from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.api.auth_dependencies import CurrentUser
from app.db import get_db_session
from app.logger import get_logger
from app.models.user import User
from app.schemas.auth import AccessTokenResponse, SignupResponse, UserLoginRequest, UserResponse, UserSignupRequest
from app.services.auth_service import AuthService

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
    payload: UserLoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AccessTokenResponse:
    """
    Authenticate a user and issue a JWT bearer token.

    This endpoint validates the submitted credentials against the stored user
    record, verifies the password hash, checks whether the user account is
    active, and returns a signed access token for authenticated API access.

    Args:
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
        response = await AuthService(session).login(payload)
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
async def get_me(current_user: CurrentUser) -> UserResponse:
    """
    Return the currently authenticated user's profile.

    This endpoint depends on bearer-token authentication. The incoming token is
    resolved by the auth dependency layer, which validates the token, loads the
    backing user record, and rejects missing, invalid, or inactive users before
    this handler is reached.

    Args:
        current_user: The authenticated user resolved from the access token.

    Returns:
        A safe user profile for the currently authenticated account.

    Raises:
        HTTPException: Returned when the profile cannot be serialized or an
            unexpected server-side error occurs.
    """
    try:
        user: User = current_user
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
