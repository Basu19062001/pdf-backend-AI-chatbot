from functools import lru_cache
from typing import List, Union

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


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

    DATABASE_URL: str = ""
    DB_SCHEME: str = "postgresql+asyncpg"
    DB_USERNAME: str = "admin"
    DB_PASSWORD: str = "password"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "pdf_chatbot_db"
    DB_ECHO: bool = False
    DB_SSLMODE: str = "disable"
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

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""
    GOOGLE_AUTH_URL: str = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL: str = "https://oauth2.googleapis.com/token"
    GOOGLE_OAUTH_STATE_COOKIE_NAME: str = "google_oauth_state"
    GOOGLE_OAUTH_STATE_EXPIRE_SECONDS: int = 300
    FRONTEND_AUTH_SUCCESS_URL: str = "http://localhost:5173/auth/google/success"
    FRONTEND_AUTH_ERROR_URL: str = "http://localhost:5173/login"

    DOCUMENT_UPLOAD_DIR: str = "uploads"
    DOCUMENT_MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024
    DOCUMENT_CHUNK_SIZE: int = 1200
    DOCUMENT_CHUNK_OVERLAP: int = 200
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_TIMEOUT_SECONDS: int = 30
    OPENAI_CHAT_TIMEOUT_SECONDS: int = 60
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    EMBEDDING_BATCH_SIZE: int = 100
    CHAT_MODEL: str = Field(
        default="gpt-4o",
        validation_alias=AliasChoices("CHAT_MODEL", "OPENAI_CHAT_MODEL"),
    )
    CHAT_MAX_CONTEXT_CHUNKS: int = 6
    CHAT_MAX_HISTORY_MESSAGES: int = 10
    CHAT_MAX_OUTPUT_TOKENS: int = 900
    CHAT_TEMPERATURE: float = 0.2
    CHAT_SYSTEM_PROMPT: str = (
        "You are a production-grade retrieval-augmented assistant for answering questions about uploaded PDFs. "
        "Your job is to help the user using only the retrieved document evidence and the visible conversation context.\n"
        "\n"
        "Core rules:\n"
        "1. Treat the retrieved document context as the source of truth.\n"
        "2. Do not invent facts, numbers, names, dates, page references, or conclusions that are not supported by the context.\n"
        "3. If the retrieved context is missing, weak, ambiguous, or insufficient, say so clearly and briefly.\n"
        "4. If the user's question is ambiguous, answer cautiously using the strongest supported interpretation and explicitly note uncertainty.\n"
        "5. If the user asks for a summary, comparison, extraction, or explanation, do it only from the provided evidence.\n"
        "6. Prefer direct, helpful answers over meta commentary.\n"
        "7. When citing evidence, mention page numbers only when they are present in the supplied context.\n"
        "8. If multiple retrieved snippets conflict, acknowledge the conflict instead of choosing an unsupported answer.\n"
        "9. Never claim the document says something unless the supplied context supports that claim.\n"
        "\n"
        "Answer style:\n"
        "- Start with the answer, not with filler.\n"
        "- Be concise for simple factual questions.\n"
        "- Use a short structured format when the question is complex.\n"
        "- If the answer is not fully supported, say: 'I don't have enough support in the retrieved document context to answer that confidently.'\n"
        "- If helpful, end with a brief note such as 'Supported by pages X-Y.'"
    )
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

    REDIS_URL: str = ""
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
        "DATABASE_URL",
        "DB_SCHEME",
        "DB_USERNAME",
        "DB_PASSWORD",
        "DB_HOST",
        "DB_NAME",
        "DB_SSLMODE",
        "DOC_ROOT_USERNAME",
        "DOC_ROOT_PASSWORD",
        "JWT_SECRET_KEY",
        "JWT_ALGORITHM",
        "JWT_ISSUER",
        "JWT_AUDIENCE",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REDIRECT_URI",
        "GOOGLE_AUTH_URL",
        "GOOGLE_TOKEN_URL",
        "GOOGLE_OAUTH_STATE_COOKIE_NAME",
        "FRONTEND_AUTH_SUCCESS_URL",
        "FRONTEND_AUTH_ERROR_URL",
        "DOCUMENT_UPLOAD_DIR",
        "OPENAI_API_KEY",
        "CHAT_MODEL",
        "CHAT_SYSTEM_PROMPT",
        "EMBEDDING_MODEL",
        "PINECONE_API_KEY",
        "PINECONE_INDEX_NAME",
        "PINECONE_INDEX_HOST",
        "PINECONE_CLOUD",
        "PINECONE_REGION",
        "PINECONE_NAMESPACE",
        "PINECONE_METRIC",
        "REDIS_URL",
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
        debug_value = values.get("DEBUG")
        debug_enabled = False
        if isinstance(debug_value, bool):
            debug_enabled = debug_value
        elif isinstance(debug_value, str):
            normalized_debug = debug_value.strip().strip('"').strip("'").lower()
            debug_enabled = normalized_debug in {"1", "true", "yes", "on", "debug", "development", "dev"}

        if debug_enabled and not values.get("LOG_LEVEL"):
            values["LOG_LEVEL"] = "DEBUG"
        return values

    @model_validator(mode="after")
    def validate_docs_credentials(self) -> "Settings":
        if self.DOCS_ENABLED and (not self.DOC_ROOT_USERNAME or not self.DOC_ROOT_PASSWORD):
            raise ValueError("DOC_ROOT_USERNAME and DOC_ROOT_PASSWORD must be set when docs are enabled")
        if self.DB_SCHEME not in {"postgresql+asyncpg", "postgresql"}:
            raise ValueError("DB_SCHEME must be 'postgresql+asyncpg' or 'postgresql'")
        if self.DB_SSLMODE not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
            raise ValueError(
                "DB_SSLMODE must be one of: disable, allow, prefer, require, verify-ca, verify-full"
            )
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
        if self.GOOGLE_CLIENT_ID or self.GOOGLE_CLIENT_SECRET or self.GOOGLE_REDIRECT_URI:
            if not self.GOOGLE_CLIENT_ID.strip():
                raise ValueError("GOOGLE_CLIENT_ID must be set when Google OAuth is enabled")
            if not self.GOOGLE_CLIENT_SECRET.strip():
                raise ValueError("GOOGLE_CLIENT_SECRET must be set when Google OAuth is enabled")
            if not self.GOOGLE_REDIRECT_URI.strip():
                raise ValueError("GOOGLE_REDIRECT_URI must be set when Google OAuth is enabled")
            if not self.GOOGLE_REDIRECT_URI.startswith(("http://", "https://")):
                raise ValueError("GOOGLE_REDIRECT_URI must be a valid URL")
            if not self.FRONTEND_AUTH_SUCCESS_URL.startswith(("http://", "https://")):
                raise ValueError("FRONTEND_AUTH_SUCCESS_URL must be a valid URL")
            if not self.FRONTEND_AUTH_ERROR_URL.startswith(("http://", "https://")):
                raise ValueError("FRONTEND_AUTH_ERROR_URL must be a valid URL")
        if self.GOOGLE_OAUTH_STATE_EXPIRE_SECONDS < 60:
            raise ValueError("GOOGLE_OAUTH_STATE_EXPIRE_SECONDS must be at least 60 seconds")
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
        if self.OPENAI_CHAT_TIMEOUT_SECONDS < 1:
            raise ValueError("OPENAI_CHAT_TIMEOUT_SECONDS must be greater than 0")
        if not self.CHAT_MODEL.strip():
            raise ValueError("CHAT_MODEL must not be empty")
        if self.CHAT_MAX_CONTEXT_CHUNKS < 1:
            raise ValueError("CHAT_MAX_CONTEXT_CHUNKS must be greater than 0")
        if self.CHAT_MAX_HISTORY_MESSAGES < 1:
            raise ValueError("CHAT_MAX_HISTORY_MESSAGES must be greater than 0")
        if self.CHAT_MAX_OUTPUT_TOKENS < 1:
            raise ValueError("CHAT_MAX_OUTPUT_TOKENS must be greater than 0")
        if not 0 <= self.CHAT_TEMPERATURE <= 2:
            raise ValueError("CHAT_TEMPERATURE must be between 0 and 2")
        if not self.CHAT_SYSTEM_PROMPT.strip():
            raise ValueError("CHAT_SYSTEM_PROMPT must not be empty")
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
        if self.DATABASE_URL:
            return self._normalize_database_url(self.DATABASE_URL)

        scheme = self.DB_SCHEME

        if scheme == "postgresql":
            scheme = "postgresql+asyncpg"

        query = {"ssl": self.DB_SSLMODE} if self.DB_SSLMODE != "disable" else {}

        return URL.create(
            drivername=scheme,
            username=self.DB_USERNAME,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
            query=query,
        ).render_as_string(hide_password=False)

    @property
    def alembic_database_url(self) -> str:
        if self.DATABASE_URL:
            return self._normalize_database_url(self.DATABASE_URL)

        query = {"ssl": self.DB_SSLMODE} if self.DB_SSLMODE != "disable" else {}

        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.DB_USERNAME,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
            query=query,
        ).render_as_string(hide_password=False)

    def _normalize_database_url(self, database_url: str) -> str:
        url = make_url(database_url)
        if url.drivername == "postgresql":
            url = url.set(drivername="postgresql+asyncpg")

        query = dict(url.query)
        sslmode = query.pop("sslmode", None)
        if sslmode and "ssl" not in query:
            query["ssl"] = sslmode
        query.pop("channel_binding", None)

        return url.set(query=query).render_as_string(hide_password=False)
    
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in {"production", "prod"}
    
    @property
    def secure_cookies(self) -> bool:
        return self.is_production
    
    @property
    def redis_url(self) -> str:
        """
        Redis URL composed from the individual Redis environment settings.

        This mirrors the database configuration style so deployment environments
        can provide Redis settings as discrete variables.
        """

        if self.REDIS_URL:
            return self.REDIS_URL

        credentials = ""
        if self.REDIS_PASSWORD:
            credentials = f":{self.REDIS_PASSWORD}@"
        return f"{self.REDIS_SCHEME}://{credentials}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
