from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin
from app.utils.id_generator import generate_entity_id


class UsageLog(TimestampMixin, Base):
    __tablename__ = "usage_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_entity_id("use"))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("chat_sessions.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(100), index=True)
    model_name: Mapped[str] = mapped_column(String(255))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    session = relationship("ChatSession", back_populates="usage_logs")
