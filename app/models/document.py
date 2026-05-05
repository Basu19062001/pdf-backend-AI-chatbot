import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    __table_args__ = (
        CheckConstraint(
            "length(trim(original_file_name)) >= 1",
            name="document_original_file_name_check",
        ),
        CheckConstraint(
            "length(trim(stored_file_name)) >= 1",
            name="document_stored_file_name_check",
        ),
        CheckConstraint(
            "length(trim(file_path)) >= 1",
            name="document_file_path_check",
        ),
        CheckConstraint(
            "file_size_bytes IS NULL OR file_size_bytes >= 0",
            name="document_file_size_check",
        ),
        CheckConstraint(
            "total_pages IS NULL OR total_pages >= 0",
            name="document_total_pages_check",
        ),
    )

    CASCADE_OPTION = "all, delete-orphan"
    default_timezone = lambda: datetime.now(timezone.utc)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    file_type: Mapped[str] = mapped_column(String(30), default="pdf", nullable=False,)

    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="uploaded", nullable=False,)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=default_timezone, nullable=False,)

    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=default_timezone, nullable=False,)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=default_timezone,
        onupdate=default_timezone,
        nullable=False,
    )

    user = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade=CASCADE_OPTION,)
    chat_sessions = relationship("ChatSession", back_populates="document", cascade=CASCADE_OPTION,)
    processing_logs = relationship("DocumentProcessingLog", back_populates="document", cascade=CASCADE_OPTION,)
    usage_logs = relationship("UsageLog", back_populates="document", cascade=CASCADE_OPTION,)