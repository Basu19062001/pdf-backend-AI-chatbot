from functools import lru_cache
from typing import List, Union

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.config import Config

config = Config(env_file="app/.env")


class Settings(BaseSettings):
    """
    Central application settings.

    Values are loaded from `app/.env` and can be overridden by environment
    variables at runtime.
    """

    PROJECT_NAME: str = config("PROJECT_NAME", cast=str, default="PDF Chatbot Backend")
    PROJECT_DESCRIPTION: str = config(
        "PROJECT_DESCRIPTION",
        cast=str,
        default="Production-style modular monolith backend for PDF chat workflows.",
    )
    VERSION: str = config("VERSION", cast=str, default="0.1.0")
    ENVIRONMENT: str = config("ENVIRONMENT", cast=str, default="development")
    DEBUG: bool = config("DEBUG", cast=bool, default=False)
    LOG_LEVEL: str = config("LOG_LEVEL", cast=str, default="INFO")

    API_V1_STR: str = config("API_V1_STR", cast=str, default="/api/v1")

    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
    ]

    DOCS_ENABLED: bool = config("DOCS_ENABLED", cast=bool, default=True)
    DOC_ROOT_USERNAME: str = config(
        "DOC_ROOT_USERNAME",
        cast=str,
        default=config("DOCS_USERNAME", cast=str, default="admin"),
    )
    DOC_ROOT_PASSWORD: str = config(
        "DOC_ROOT_PASSWORD",
        cast=str,
        default=config("DOCS_PASSWORD", cast=str, default="docs-password"),
    )
    DOCS_URL: str = config("DOCS_URL", cast=str, default="/docs")
    REDOC_URL: str = config("REDOC_URL", cast=str, default="/redoc")
    OPENAPI_URL: str = config("OPENAPI_URL", cast=str, default="/openapi.json")

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("DOCS_URL", "REDOC_URL", "OPENAPI_URL", "API_V1_STR", mode="before")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        if not value:
            return "/"
        return value if value.startswith("/") else f"/{value}"

    @model_validator(mode="after")
    def validate_docs_credentials(self) -> "Settings":
        if self.DOCS_ENABLED and (not self.DOC_ROOT_USERNAME or not self.DOC_ROOT_PASSWORD):
            raise ValueError("DOC_ROOT_USERNAME and DOC_ROOT_PASSWORD must be set when docs are enabled")
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
