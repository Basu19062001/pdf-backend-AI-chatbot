import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UsageLog(Base):
    __tablename__ = "usage_logs"
    
    __table_args__ = (
        CheckConstraint(
            "length(trim(action_type)) >= 1",
            name="usage_log_action_type_check",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="usage_log_input_tokens_check",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="usage_log_output_tokens_check",
        ),
        CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="usage_log_total_tokens_check",
        ),
        CheckConstraint(
            "cost IS NULL OR cost >= 0",
            name="usage_log_cost_check",
        ),
    )

    default_timezone = lambda: datetime.now(timezone.utc)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=default_timezone, nullable=False)

    user = relationship("User", back_populates="usage_logs")
    document = relationship("Document", back_populates="usage_logs")
    session = relationship("ChatSession", back_populates="usage_logs")