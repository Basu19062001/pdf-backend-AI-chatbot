from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin
from app.utils.id_generator import generate_entity_id


class ChatSession(TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_entity_id("ses"))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="active", index=True)

    user = relationship("User", back_populates="chat_sessions")
    document = relationship("Document")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    usage_logs = relationship("UsageLog", back_populates="session", cascade="all, delete-orphan")
