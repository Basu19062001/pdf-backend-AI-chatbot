from __future__ import annotations

import base64
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, status

from app.core.config import settings
from app.utils import utc_now

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_SALT_BYTES = 16
SCRYPT_KEY_BYTES = 32


def hash_password(password: str) -> str:
    """Return a salted scrypt hash for a plain-text password."""
    salt = os.urandom(SCRYPT_SALT_BYTES)
    derived_key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_KEY_BYTES,
    )
    return (
        f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$"
        f"{base64.urlsafe_b64encode(salt).decode('utf-8')}$"
        f"{base64.urlsafe_b64encode(derived_key).decode('utf-8')}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    """Safely verify a plain-text password against a stored scrypt hash."""
    try:
        algorithm, n_value, r_value, p_value, encoded_salt, encoded_key = password_hash.split("$")
        if algorithm != "scrypt":
            return False

        salt = base64.urlsafe_b64decode(encoded_salt.encode("utf-8"))
        expected_key = base64.urlsafe_b64decode(encoded_key.encode("utf-8"))
        derived_key = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n_value),
            r=int(r_value),
            p=int(p_value),
            dklen=len(expected_key),
        )
        return hmac.compare_digest(derived_key, expected_key)
    except (ValueError, TypeError):
        return False


def hash_token(token: str) -> str:
    """Return a deterministic SHA-256 hash for a signed token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_signed_token(
    subject: str,
    session_id: uuid.UUID,
    token_jti: str,
    token_type: str,
    expires_delta: timedelta,
    additional_claims: dict[str, Any] | None = None,
) -> tuple[str, datetime, datetime]:
    """Create a signed JWT with standard registered claims."""
    issued_at = utc_now()
    expires_at = issued_at + expires_delta

    payload: dict[str, Any] = {
        "sub": subject,
        "sid": str(session_id),
        "jti": token_jti,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int(issued_at.timestamp()),
        "nbf": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "type": token_type,
    }
    if additional_claims:
        payload.update(additional_claims)

    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, issued_at, expires_at


def create_access_token(
    subject: str,
    session_id: uuid.UUID,
    token_jti: str,
    additional_claims: dict[str, Any] | None = None,
) -> tuple[str, datetime, datetime]:
    """Create a signed JWT access token with standard registered claims."""
    return _create_signed_token(
        subject=subject,
        session_id=session_id,
        token_jti=token_jti,
        token_type="access",
        expires_delta=timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        additional_claims=additional_claims,
    )


def create_refresh_token(
    subject: str,
    session_id: uuid.UUID,
    token_jti: str,
) -> tuple[str, datetime, datetime]:
    """Create a signed JWT refresh token with standard registered claims."""
    return _create_signed_token(
        subject=subject,
        session_id=session_id,
        token_jti=token_jti,
        token_type="refresh",
        expires_delta=timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )


def _decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Decode and validate a signed JWT for the expected token type."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("type") != expected_type or not payload.get("sub") or not payload.get("sid") or not payload.get("jti"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token."""
    return _decode_token(token, expected_type="access")


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decode and validate a refresh token."""
    return _decode_token(token, expected_type="refresh")
