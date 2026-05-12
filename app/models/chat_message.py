import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils import utc_now


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="chat_message_role_check",
        ),
        CheckConstraint(
            "length(trim(content)) >= 1",
            name="chat_message_content_check",
        ),
        CheckConstraint(
            "prompt_tokens IS NULL OR prompt_tokens >= 0",
            name="chat_message_prompt_tokens_check",
        ),
        CheckConstraint(
            "completion_tokens IS NULL OR completion_tokens >= 0",
            name="chat_message_completion_tokens_check",
        ),
        CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="chat_message_total_tokens_check",
        ),
        CheckConstraint(
            "estimated_cost IS NULL OR estimated_cost >= 0",
            name="chat_message_estimated_cost_check",
        ),
    )

    CASCADE_OPTION = "all, delete-orphan"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    session = relationship("ChatSession", back_populates="messages")
    sources = relationship("MessageSource", back_populates="message", cascade="all, delete-orphan")
