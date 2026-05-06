from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class UserSignupRequest(BaseModel):
    """Payload used to create a new authenticated user account."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "full_name": "Ava Sharma",
                "email": "ava@example.com",
                "password": "StrongPass123!",
            }
        },
    )

    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if len(normalized) < 2:
            raise ValueError("full_name must contain at least 2 non-space characters")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> EmailStr:
        return value.lower()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        checks = (
            any(char.islower() for char in raw),
            any(char.isupper() for char in raw),
            any(char.isdigit() for char in raw),
            any(not char.isalnum() for char in raw),
        )
        if not all(checks):
            raise ValueError(
                "password must include uppercase, lowercase, numeric, and special characters"
            )
        return value


class UserLoginRequest(BaseModel):
    """Payload used to authenticate a user and mint an access token."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "email": "ava@example.com",
                "password": "StrongPass123!",
            }
        },
    )

    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> EmailStr:
        return value.lower()


class UserResponse(BaseModel):
    """Safe user profile returned from auth endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AccessTokenResponse(BaseModel):
    """Bearer token response returned after successful authentication."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600,
                "user": {
                    "id": "6dfdf88e-3412-4701-885d-8b4c9c21db12",
                    "full_name": "Ava Sharma",
                    "email": "ava@example.com",
                    "role": "user",
                    "is_active": True,
                    "created_at": "2026-05-06T12:00:00Z",
                    "updated_at": "2026-05-06T12:00:00Z",
                },
            }
        }
    )

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class SignupResponse(BaseModel):
    """Response returned after successful account creation."""

    user: UserResponse
    message: str = "User account created successfully"
