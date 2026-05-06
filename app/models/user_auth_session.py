import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserAuthSession(Base):
    __tablename__ = "user_auth_sessions"

    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(active_sessions) = 'array'",
            name="user_auth_session_active_sessions_array_check",
        ),
    )

    default_timezone = lambda: datetime.now(timezone.utc)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )

    active_sessions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=default_timezone,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=default_timezone,
        onupdate=default_timezone,
        nullable=False,
    )

    user = relationship("User", back_populates="auth_sessions")
