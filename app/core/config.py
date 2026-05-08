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

    JWT_SECRET_KEY: str = "change-me-in-production-at-least-32chars"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "pdf-chatbot-backend"
    JWT_AUDIENCE: str = "pdf-chatbot-clients"

    DOCUMENT_UPLOAD_DIR: str = "uploads"
    DOCUMENT_MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024
    DOCUMENT_CHUNK_SIZE: int = 1200
    DOCUMENT_CHUNK_OVERLAP: int = 200
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_TIMEOUT_SECONDS: int = 30
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    EMBEDDING_BATCH_SIZE: int = 100
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX_NAME: str = ""
    PINECONE_INDEX_HOST: str = ""
    PINECONE_CLOUD: str = "aws"
    PINECONE_REGION: str = "us-east-1"
    PINECONE_NAMESPACE: str = ""
    PINECONE_METRIC: str = "cosine"
    PINECONE_UPSERT_BATCH_SIZE: int = 100
    PINECONE_INDEX_TIMEOUT_SECONDS: int = 60
    PINECONE_CREATE_INDEX_IF_MISSING: bool = True
    PDF_ANALYSIS_MIN_WORDS_FOR_TEXT: int = 20
    PDF_ANALYSIS_IMAGE_AREA_THRESHOLD: float = 0.35
    PDF_ANALYSIS_OCR_IMAGE_AREA_THRESHOLD: float = 0.55
    PDF_ANALYSIS_MIN_TABLE_ROWS: int = 2
    PDF_ANALYSIS_MIN_TABLE_COLUMNS: int = 2
    PDF_ANALYSIS_TABLE_DENSITY_THRESHOLD: float = 0.3

    REDIS_ENABLED: bool = True
    REDIS_SCHEME: str = "redis"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_CONNECT_TIMEOUT: int = 5
    REDIS_KEY_PREFIX: str = "pdf-chatbot"

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
        "JWT_SECRET_KEY",
        "JWT_ALGORITHM",
        "JWT_ISSUER",
        "JWT_AUDIENCE",
        "DOCUMENT_UPLOAD_DIR",
        "OPENAI_API_KEY",
        "EMBEDDING_MODEL",
        "PINECONE_API_KEY",
        "PINECONE_INDEX_NAME",
        "PINECONE_INDEX_HOST",
        "PINECONE_CLOUD",
        "PINECONE_REGION",
        "PINECONE_NAMESPACE",
        "PINECONE_METRIC",
        "REDIS_SCHEME",
        "REDIS_HOST",
        "REDIS_PASSWORD",
        "REDIS_KEY_PREFIX",
        mode="before",
    )
    @classmethod
    def strip_quotes(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().strip('"').strip("'")
        return value

    @field_validator(
        "DEBUG",
        "DB_ECHO",
        "DB_POOL_PRE_PING",
        "DOCS_ENABLED",
        "REDIS_ENABLED",
        "PINECONE_CREATE_INDEX_IF_MISSING",
        mode="before",
    )
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
        if not values.get("REDIS_KEY_PREFIX") and values.get("REDIS_TOKEN_KEY_PREFIX"):
            values["REDIS_KEY_PREFIX"] = values["REDIS_TOKEN_KEY_PREFIX"]
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
        if len(self.JWT_SECRET_KEY.strip()) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        if self.JWT_ALGORITHM != "HS256":
            raise ValueError("JWT_ALGORITHM must be 'HS256'")
        if self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES < 1:
            raise ValueError("JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be greater than 0")
        if self.JWT_REFRESH_TOKEN_EXPIRE_DAYS < 1:
            raise ValueError("JWT_REFRESH_TOKEN_EXPIRE_DAYS must be greater than 0")
        if not self.DOCUMENT_UPLOAD_DIR.strip():
            raise ValueError("DOCUMENT_UPLOAD_DIR must not be empty")
        if self.DOCUMENT_MAX_FILE_SIZE_BYTES < 1:
            raise ValueError("DOCUMENT_MAX_FILE_SIZE_BYTES must be greater than 0")
        if self.DOCUMENT_CHUNK_SIZE < 1:
            raise ValueError("DOCUMENT_CHUNK_SIZE must be greater than 0")
        if self.DOCUMENT_CHUNK_OVERLAP < 0:
            raise ValueError("DOCUMENT_CHUNK_OVERLAP must be greater than or equal to 0")
        if self.DOCUMENT_CHUNK_OVERLAP >= self.DOCUMENT_CHUNK_SIZE:
            raise ValueError("DOCUMENT_CHUNK_OVERLAP must be smaller than DOCUMENT_CHUNK_SIZE")
        if self.OPENAI_EMBEDDING_TIMEOUT_SECONDS < 1:
            raise ValueError("OPENAI_EMBEDDING_TIMEOUT_SECONDS must be greater than 0")
        if not self.EMBEDDING_MODEL.strip():
            raise ValueError("EMBEDDING_MODEL must not be empty")
        if self.EMBEDDING_DIMENSION < 1:
            raise ValueError("EMBEDDING_DIMENSION must be greater than 0")
        if self.EMBEDDING_BATCH_SIZE < 1:
            raise ValueError("EMBEDDING_BATCH_SIZE must be greater than 0")
        if self.PINECONE_INDEX_NAME and not self.PINECONE_INDEX_NAME.replace("-", "").replace("_", "").isalnum():
            raise ValueError("PINECONE_INDEX_NAME may contain only letters, numbers, hyphens, and underscores")
        if self.PINECONE_CLOUD not in {"aws", "gcp", "azure"}:
            raise ValueError("PINECONE_CLOUD must be one of: aws, gcp, azure")
        if not self.PINECONE_REGION.strip():
            raise ValueError("PINECONE_REGION must not be empty")
        if self.PINECONE_METRIC not in {"cosine", "dotproduct", "euclidean"}:
            raise ValueError("PINECONE_METRIC must be one of: cosine, dotproduct, euclidean")
        if self.PINECONE_UPSERT_BATCH_SIZE < 1:
            raise ValueError("PINECONE_UPSERT_BATCH_SIZE must be greater than 0")
        if self.PINECONE_INDEX_TIMEOUT_SECONDS < 1:
            raise ValueError("PINECONE_INDEX_TIMEOUT_SECONDS must be greater than 0")
        if self.PDF_ANALYSIS_MIN_WORDS_FOR_TEXT < 0:
            raise ValueError("PDF_ANALYSIS_MIN_WORDS_FOR_TEXT must be greater than or equal to 0")
        if not 0 <= self.PDF_ANALYSIS_IMAGE_AREA_THRESHOLD <= 1:
            raise ValueError("PDF_ANALYSIS_IMAGE_AREA_THRESHOLD must be between 0 and 1")
        if not 0 <= self.PDF_ANALYSIS_OCR_IMAGE_AREA_THRESHOLD <= 1:
            raise ValueError("PDF_ANALYSIS_OCR_IMAGE_AREA_THRESHOLD must be between 0 and 1")
        if self.PDF_ANALYSIS_OCR_IMAGE_AREA_THRESHOLD < self.PDF_ANALYSIS_IMAGE_AREA_THRESHOLD:
            raise ValueError(
                "PDF_ANALYSIS_OCR_IMAGE_AREA_THRESHOLD must be greater than or equal to PDF_ANALYSIS_IMAGE_AREA_THRESHOLD"
            )
        if self.PDF_ANALYSIS_MIN_TABLE_ROWS < 1:
            raise ValueError("PDF_ANALYSIS_MIN_TABLE_ROWS must be greater than 0")
        if self.PDF_ANALYSIS_MIN_TABLE_COLUMNS < 1:
            raise ValueError("PDF_ANALYSIS_MIN_TABLE_COLUMNS must be greater than 0")
        if not 0 <= self.PDF_ANALYSIS_TABLE_DENSITY_THRESHOLD <= 1:
            raise ValueError("PDF_ANALYSIS_TABLE_DENSITY_THRESHOLD must be between 0 and 1")
        if self.REDIS_SCHEME not in {"redis", "rediss"}:
            raise ValueError("REDIS_SCHEME must be 'redis' or 'rediss'")
        if not self.REDIS_HOST.strip():
            raise ValueError("REDIS_HOST must not be empty")
        if self.REDIS_PORT < 1:
            raise ValueError("REDIS_PORT must be greater than 0")
        if self.REDIS_DB < 0:
            raise ValueError("REDIS_DB must be greater than or equal to 0")
        if self.REDIS_CONNECT_TIMEOUT < 1:
            raise ValueError("REDIS_CONNECT_TIMEOUT must be greater than 0")
        if not self.REDIS_KEY_PREFIX.strip():
            raise ValueError("REDIS_KEY_PREFIX must not be empty")
        return self

    @property
    def database_url(self) -> str:
        scheme = self.DB_SCHEME
        if scheme == "postgresql":
            scheme = "postgresql+asyncpg"
        return f"{scheme}://{self.DB_USERNAME}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def alembic_database_url(self) -> str:
        """
        Database URL consumed by Alembic.

        Alembic in this project uses the same connection settings as the app
        itself so there is a single source of truth for database configuration.
        """

        return self.database_url

    @property
    def redis_url(self) -> str:
        """
        Redis URL composed from the individual Redis environment settings.

        This mirrors the database configuration style so deployment environments
        can provide Redis settings as discrete variables.
        """

        credentials = ""
        if self.REDIS_PASSWORD:
            credentials = f":{self.REDIS_PASSWORD}@"
        return f"{self.REDIS_SCHEME}://{credentials}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
