from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin
from app.utils.id_generator import generate_entity_id


class MessageSource(TimestampMixin, Base):
    __tablename__ = "message_sources"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_entity_id("src"))
    message_id: Mapped[str] = mapped_column(ForeignKey("chat_messages.id"), index=True)
    document_chunk_id: Mapped[str | None] = mapped_column(ForeignKey("document_chunks.id"), nullable=True)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    message = relationship("ChatMessage", back_populates="sources")
