import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils import utc_now


class MessageSource(Base):
    __tablename__ = "message_sources"
    
    __table_args__ = (
        UniqueConstraint(
            "message_id",
            "chunk_id",
            name="uq_message_sources_message_id_chunk_id",
        ),
        CheckConstraint(
            "source_rank IS NULL OR source_rank >= 1",
            name="message_source_rank_check",
        ),
        CheckConstraint(
            "similarity_score IS NULL OR (similarity_score >= 0 AND similarity_score <= 1)",
            name="message_source_similarity_score_check",
        ),
        CheckConstraint(
            "page_number_start IS NULL OR page_number_start >= 1",
            name="message_source_page_start_check",
        ),
        CheckConstraint(
            "page_number_end IS NULL OR page_number_end >= 1",
            name="message_source_page_end_check",
        ),
        CheckConstraint(
            "page_number_start IS NULL OR page_number_end IS NULL OR page_number_end >= page_number_start",
            name="message_source_page_range_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    page_number_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_number_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quoted_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    message = relationship("ChatMessage", back_populates="sources")
    chunk = relationship("DocumentChunk", back_populates="message_sources")
