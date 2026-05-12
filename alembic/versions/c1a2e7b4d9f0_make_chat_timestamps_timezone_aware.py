"""make chat timestamps timezone aware

Revision ID: c1a2e7b4d9f0
Revises: 92d4c8a1e5bf
Create Date: 2026-05-12 10:05:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1a2e7b4d9f0"
down_revision = "92d4c8a1e5bf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "chat_sessions",
        "started_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="started_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "chat_sessions",
        "last_message_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="last_message_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "chat_sessions",
        "created_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "chat_sessions",
        "updated_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="updated_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "usage_logs",
        "created_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    op.alter_column(
        "usage_logs",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "chat_sessions",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="updated_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "chat_sessions",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "chat_sessions",
        "last_message_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=True,
        postgresql_using="last_message_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "chat_sessions",
        "started_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="started_at AT TIME ZONE 'UTC'",
    )
