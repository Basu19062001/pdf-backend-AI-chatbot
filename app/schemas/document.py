import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    original_file_name: str
    stored_file_name: str
    file_path: str
    file_url: str | None
    file_type: str
    file_size_bytes: int | None
    total_pages: int | None
    status: str
    error_message: str | None
    uploaded_at: datetime
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]


class DocumentUploadResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    pages: int
    chunks: int
