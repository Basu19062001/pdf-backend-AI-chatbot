from functools import lru_cache
from typing import List, Union

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application settings.

    Values are loaded from `app/.env` and can be overridden by environment
    variables at runtime.
    """

    PROJECT_NAME: str = "PDF Chatbot Backend"
    PROJECT_DESCRIPTION: str = "Production-style modular monolith backend for PDF chat workflows."
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    API_V1_STR: str = "/api/v1"

    DB_SCHEME: str = "postgresql+asyncpg"
    DB_USERNAME: str = "admin"
    DB_PASSWORD: str = "password"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "pdf_chatbot_db"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_PRE_PING: bool = True
    DB_CONNECT_TIMEOUT: int = 10

    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
    ]

    DOCS_ENABLED: bool = True
    DOC_ROOT_USERNAME: str = "admin"
    DOC_ROOT_PASSWORD: str = "docs-password"
    DOCS_URL: str = "/docs"
    REDOC_URL: str = "/redoc"
    OPENAPI_URL: str = "/openapi.json"

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        env_file="app/.env",
        env_file_encoding="utf-8",
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "PROJECT_NAME",
        "PROJECT_DESCRIPTION",
        "VERSION",
        "ENVIRONMENT",
        "LOG_LEVEL",
        "DB_SCHEME",
        "DB_USERNAME",
        "DB_PASSWORD",
        "DB_HOST",
        "DB_NAME",
        "DOC_ROOT_USERNAME",
        "DOC_ROOT_PASSWORD",
        mode="before",
    )
    @classmethod
    def strip_quotes(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().strip('"').strip("'")
        return value

    @field_validator("DEBUG", "DB_ECHO", "DB_POOL_PRE_PING", "DOCS_ENABLED", mode="before")
    @classmethod
    def parse_boolish(cls, value: object) -> object:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().strip('"').strip("'").lower()
            if normalized in {"1", "true", "yes", "on", "debug", "development", "dev"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "production", "prod"}:
                return False
        return value

    @field_validator("DOCS_URL", "REDOC_URL", "OPENAPI_URL", "API_V1_STR", mode="before")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        if not value:
            return "/"
        return value if value.startswith("/") else f"/{value}"

    @model_validator(mode="before")
    @classmethod
    def map_legacy_docs_credentials(cls, values: object) -> object:
        if not isinstance(values, dict):
            return values

        if not values.get("DOC_ROOT_USERNAME") and values.get("DOCS_USERNAME"):
            values["DOC_ROOT_USERNAME"] = values["DOCS_USERNAME"]
        if not values.get("DOC_ROOT_PASSWORD") and values.get("DOCS_PASSWORD"):
            values["DOC_ROOT_PASSWORD"] = values["DOCS_PASSWORD"]
        return values

    @model_validator(mode="after")
    def validate_docs_credentials(self) -> "Settings":
        if self.DOCS_ENABLED and (not self.DOC_ROOT_USERNAME or not self.DOC_ROOT_PASSWORD):
            raise ValueError("DOC_ROOT_USERNAME and DOC_ROOT_PASSWORD must be set when docs are enabled")
        if self.DB_SCHEME not in {"postgresql+asyncpg", "postgresql"}:
            raise ValueError("DB_SCHEME must be 'postgresql+asyncpg' or 'postgresql'")
        if self.DB_PORT < 1:
            raise ValueError("DB_PORT must be greater than 0")
        if self.DB_POOL_SIZE < 1:
            raise ValueError("DB_POOL_SIZE must be greater than 0")
        if self.DB_MAX_OVERFLOW < 0:
            raise ValueError("DB_MAX_OVERFLOW must be greater than or equal to 0")
        if self.DB_POOL_TIMEOUT < 1:
            raise ValueError("DB_POOL_TIMEOUT must be greater than 0")
        if self.DB_POOL_RECYCLE < -1:
            raise ValueError("DB_POOL_RECYCLE must be -1 or greater")
        if self.DB_CONNECT_TIMEOUT < 1:
            raise ValueError("DB_CONNECT_TIMEOUT must be greater than 0")
        return self

    @property
    def database_url(self) -> str:
        scheme = self.DB_SCHEME
        if scheme == "postgresql":
            scheme = "postgresql+asyncpg"
        return f"{scheme}://{self.DB_USERNAME}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
