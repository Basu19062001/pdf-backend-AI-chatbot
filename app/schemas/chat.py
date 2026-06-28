from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: uuid.UUID
    source_rank: int | None = None
    similarity_score: float | None = None
    page_number_start: int | None = None
    page_number_end: int | None = None
    quoted_text: str | None = None


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1)
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
    llm_model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    created_at: datetime
    sources: list[ChatSourceResponse] = Field(default_factory=list)


class ChatSessionCreate(BaseModel):
    document_id: uuid.UUID
    title: str | None = None


class ChatSessionSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    document_id: uuid.UUID
    title: str | None = None
    status: str
    started_at: datetime
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ChatSessionResponse(ChatSessionSummaryResponse):
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionSummaryResponse]


class ChatTurnResponse(BaseModel):
    session: ChatSessionResponse
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
