import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils import utc_now


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_id_chunk_index",
        ),
        CheckConstraint(
            "chunk_index >= 0",
            name="document_chunk_index_check",
        ),
        CheckConstraint(
            "page_number_start IS NULL OR page_number_start >= 1",
            name="document_chunk_page_start_check",
        ),
        CheckConstraint(
            "page_number_end IS NULL OR page_number_end >= 1",
            name="document_chunk_page_end_check",
        ),
        CheckConstraint(
            "page_number_start IS NULL OR page_number_end IS NULL OR page_number_end >= page_number_start",
            name="document_chunk_page_range_check",
        ),
        CheckConstraint(
            "length(trim(chunk_text)) >= 1",
            name="document_chunk_text_check",
        ),
        CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="document_chunk_token_count_check",
        ),
    )

    CASCADE_OPTION = "all, delete-orphan"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    pinecone_vector_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False,)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False,)
    page_number_start: Mapped[int | None] = mapped_column(Integer, nullable=True,)
    page_number_end: Mapped[int | None] = mapped_column(Integer, nullable=True,)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False,)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True,)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True,)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False,)

    document = relationship("Document", back_populates="chunks",)
    message_sources = relationship("MessageSource", back_populates="chunk", cascade=CASCADE_OPTION,)
