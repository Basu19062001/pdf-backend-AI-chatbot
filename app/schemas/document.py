from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentCreate(BaseModel):
    title: str
    original_filename: str
    storage_path: str
    mime_type: str = "application/pdf"
    user_id: str | None = None
    summary: str | None = None


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str | None
    title: str
    original_filename: str
    storage_path: str
    mime_type: str
    status: str
    summary: str | None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
