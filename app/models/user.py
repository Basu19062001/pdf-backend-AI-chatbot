import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            r"email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'",
            name="email_format_check",
        ),
        CheckConstraint(
            "length(trim(full_name)) >= 2",
            name="full_name_length_check",
        ),
    )

    CASCADE_OPTION = "all, delete-orphan"
    default_timezone = lambda: datetime.now(timezone.utc)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=default_timezone, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=default_timezone,
        onupdate=default_timezone,
        nullable=False,
    )

    documents = relationship("Document", back_populates="user", cascade=CASCADE_OPTION)
    chat_sessions = relationship("ChatSession", back_populates="user", cascade=CASCADE_OPTION)
    usage_logs = relationship("UsageLog", back_populates="user", cascade=CASCADE_OPTION)