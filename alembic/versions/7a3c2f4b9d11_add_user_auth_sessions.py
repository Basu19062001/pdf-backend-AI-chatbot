"""add user auth sessions

Revision ID: 7a3c2f4b9d11
Revises: 3bd016ede9f5
Create Date: 2026-05-06 13:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7a3c2f4b9d11"
down_revision = "3bd016ede9f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_auth_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_jti", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=255), nullable=True),
        sa.Column("device_name", sa.String(length=255), nullable=True),
        sa.Column("device_type", sa.String(length=50), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "device_type IS NULL OR length(trim(device_type)) >= 1",
            name=op.f("ck_user_auth_sessions_user_auth_session_device_type_check"),
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name=op.f("ck_user_auth_sessions_user_auth_session_expiry_window_check"),
        ),
        sa.CheckConstraint(
            "length(trim(token_hash)) = 64",
            name=op.f("ck_user_auth_sessions_user_auth_session_token_hash_check"),
        ),
        sa.CheckConstraint(
            "length(trim(token_jti)) >= 1",
            name=op.f("ck_user_auth_sessions_user_auth_session_token_jti_check"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_auth_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_auth_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_auth_sessions_token_hash")),
        sa.UniqueConstraint("token_jti", name=op.f("uq_user_auth_sessions_token_jti")),
    )
    op.create_index(
        op.f("ix_user_auth_sessions_user_auth_sessions_device_id"),
        "user_auth_sessions",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_auth_sessions_user_auth_sessions_expires_at"),
        "user_auth_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_auth_sessions_user_auth_sessions_token_jti"),
        "user_auth_sessions",
        ["token_jti"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_auth_sessions_user_auth_sessions_user_id"),
        "user_auth_sessions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_user_auth_sessions_user_auth_sessions_user_id"),
        table_name="user_auth_sessions",
    )
    op.drop_index(
        op.f("ix_user_auth_sessions_user_auth_sessions_token_jti"),
        table_name="user_auth_sessions",
    )
    op.drop_index(
        op.f("ix_user_auth_sessions_user_auth_sessions_expires_at"),
        table_name="user_auth_sessions",
    )
    op.drop_index(
        op.f("ix_user_auth_sessions_user_auth_sessions_device_id"),
        table_name="user_auth_sessions",
    )
    op.drop_table("user_auth_sessions")
