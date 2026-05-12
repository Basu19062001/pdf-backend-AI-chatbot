from __future__ import annotations

from dataclasses import dataclass
import re

from app.core.config import settings


@dataclass(slots=True)
class TextChunk:
    chunk_index: int
    page_number_start: int
    page_number_end: int
    chunk_text: str
    token_count: int


class ChunkService:
    """Split extracted PDF text into page-aware chunks."""

    def split_pages(
        self,
        page_texts: list[str],
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> list[TextChunk]:
        resolved_chunk_size = chunk_size or settings.DOCUMENT_CHUNK_SIZE
        resolved_chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.DOCUMENT_CHUNK_OVERLAP
        chunks: list[TextChunk] = []
        chunk_index = 0

        for page_number, page_text in enumerate(page_texts, start=1):
            normalized_text = self._normalize_text(page_text)
            if not normalized_text:
                continue

            start_index = 0
            while start_index < len(normalized_text):
                end_index = min(len(normalized_text), start_index + resolved_chunk_size)
                if end_index < len(normalized_text):
                    split_index = normalized_text.rfind(" ", start_index, end_index)
                    if split_index > start_index + (resolved_chunk_size // 2):
                        end_index = split_index

                chunk_text = normalized_text[start_index:end_index].strip()
                if chunk_text:
                    chunks.append(
                        TextChunk(
                            chunk_index=chunk_index,
                            page_number_start=page_number,
                            page_number_end=page_number,
                            chunk_text=chunk_text,
                            token_count=len(chunk_text.split()),
                        )
                    )
                    chunk_index += 1

                if end_index >= len(normalized_text):
                    break

                start_index = max(end_index - resolved_chunk_overlap, start_index + 1)

        return chunks

    def _normalize_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()
