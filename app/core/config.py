from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PDF Chatbot Backend"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    database_url: str = Field(default="sqlite:///./pdf_chatbot.db", alias="DATABASE_URL")
    uploads_dir: str = Field(default="uploads", alias="UPLOADS_DIR")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    pinecone_api_key: str | None = Field(default=None, alias="PINECONE_API_KEY")
    pinecone_index_name: str | None = Field(default=None, alias="PINECONE_INDEX_NAME")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
