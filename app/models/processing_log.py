from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin
from app.utils.id_generator import generate_entity_id


class ProcessingLog(TimestampMixin, Base):
    __tablename__ = "processing_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_entity_id("prc"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    step: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(50), index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    document = relationship("Document", back_populates="processing_logs")
