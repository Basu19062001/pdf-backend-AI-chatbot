from datetime import datetime
from decimal import Decimal
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatMessageSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: uuid.UUID
    source_rank: int | None = None
    similarity_score: float | None = None
    page_number_start: int | None = None
    page_number_end: int | None = None
    quoted_text: str | None = None


class ChatMessageCreate(BaseModel):
    role: str = "user"
    content: str
    model_name: str | None = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("content must not be empty")
        return normalized


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    model_name: str | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: Decimal | None = None
    created_at: datetime
    sources: list[ChatMessageSourceResponse] = Field(default_factory=list)


class ChatSessionCreate(BaseModel):
    document_id: uuid.UUID
    title: str | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    document_id: uuid.UUID
    title: str | None
    status: str
    started_at: datetime
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionResponse]
