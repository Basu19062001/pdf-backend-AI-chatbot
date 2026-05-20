"""make chat timestamps timezone aware

Revision ID: b58c4f7d2e91
Revises: 92d4c8a1e5bf
Create Date: 2026-05-20 12:45:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b58c4f7d2e91"
down_revision = "92d4c8a1e5bf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column_name, nullable in (
        ("started_at", False),
        ("last_message_at", True),
        ("created_at", False),
        ("updated_at", False),
    ):
        op.alter_column(
            "chat_sessions",
            column_name,
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=nullable,
            postgresql_using=f"{column_name} AT TIME ZONE 'UTC'",
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
    for column_name, nullable in (
        ("started_at", False),
        ("last_message_at", True),
        ("created_at", False),
        ("updated_at", False),
    ):
        op.alter_column(
            "chat_sessions",
            column_name,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=nullable,
            postgresql_using=f"{column_name} AT TIME ZONE 'UTC'",
        )

    op.alter_column(
        "usage_logs",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
