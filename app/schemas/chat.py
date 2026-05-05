from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatMessageCreate(BaseModel):
    role: str
    content: str
    model_name: str | None = None


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    model_name: str | None
    created_at: datetime
    updated_at: datetime


class ChatSessionCreate(BaseModel):
    title: str
    user_id: str | None = None
    document_id: str | None = None


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str | None
    document_id: str | None
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionResponse]
