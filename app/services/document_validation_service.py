from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

ALLOWED_PDF_EXTENSIONS = {".pdf"}
ALLOWED_PDF_MIME_TYPES = {"application/pdf", "application/x-pdf"}


@dataclass(slots=True)
class ValidatedUpload:
    original_file_name: str
    content_type: str
    file_size_bytes: int
    content: bytes


class DocumentValidationService:
    """Validate incoming PDF uploads and extracted PDF content."""

    async def validate_upload(self, upload_file: UploadFile) -> ValidatedUpload:
        original_file_name = Path(upload_file.filename or "").name.strip()
        if not original_file_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A PDF file name is required",
            )

        if Path(original_file_name).suffix.lower() not in ALLOWED_PDF_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF files are supported",
            )

        content_type = (upload_file.content_type or "").strip().lower()
        if content_type and content_type not in ALLOWED_PDF_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid PDF content type",
            )

        content = await upload_file.read()
        file_size_bytes = len(content)
        if file_size_bytes == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded PDF file is empty",
            )

        if file_size_bytes > settings.DOCUMENT_MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Uploaded PDF file exceeds the maximum allowed size",
            )

        return ValidatedUpload(
            original_file_name=original_file_name,
            content_type=content_type or "application/pdf",
            file_size_bytes=file_size_bytes,
            content=content,
        )

    def validate_extracted_pages(self, page_texts: list[str]) -> list[str]:
        if not page_texts:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No pages could be extracted from the uploaded PDF",
            )

        if not any(page.strip() for page in page_texts):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Uploaded PDF does not contain extractable text",
            )

        return page_texts
