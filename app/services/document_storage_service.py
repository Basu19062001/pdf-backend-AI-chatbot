from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import re
import uuid

from fastapi import HTTPException, status

from app.core.config import settings
from app.logger import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class StoredDocumentFile:
    original_file_name: str
    stored_file_name: str
    absolute_path: Path
    relative_path: str


class DocumentStorageService:
    """Persist uploaded PDF files to the configured local storage directory."""

    def __init__(self):
        self.upload_dir = Path(settings.DOCUMENT_UPLOAD_DIR)

    async def store_pdf(self, original_file_name: str, content: bytes) -> StoredDocumentFile:
        stored_file_name = self._build_stored_file_name(original_file_name)
        absolute_path = self.upload_dir / stored_file_name
        relative_path = absolute_path.as_posix()

        try:
            await asyncio.to_thread(self.upload_dir.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(absolute_path.write_bytes, content)
        except OSError as exc:
            logger.exception("Failed to store uploaded PDF '%s'.", original_file_name)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to store the uploaded PDF",
            ) from exc

        return StoredDocumentFile(
            original_file_name=original_file_name,
            stored_file_name=stored_file_name,
            absolute_path=absolute_path,
            relative_path=relative_path,
        )

    async def delete_file(self, absolute_path: Path) -> None:
        try:
            if absolute_path.exists():
                await asyncio.to_thread(absolute_path.unlink)
        except OSError:
            logger.exception("Failed to delete stored PDF '%s'.", absolute_path)

    def _build_stored_file_name(self, original_file_name: str) -> str:
        stem = Path(original_file_name).stem
        normalized_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
        safe_stem = normalized_stem or "document"
        return f"{safe_stem}-{uuid.uuid4().hex}.pdf"
