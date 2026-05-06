"""refactor user auth sessions to one row per user

Revision ID: 92d4c8a1e5bf
Revises: 7a3c2f4b9d11
Create Date: 2026-05-06 15:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "92d4c8a1e5bf"
down_revision = "7a3c2f4b9d11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_auth_sessions_v2",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "active_sessions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(active_sessions) = 'array'",
            name=op.f("ck_user_auth_sessions_v2_active_sessions_array_check"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_auth_sessions_v2_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_auth_sessions_v2")),
        sa.UniqueConstraint("user_id", name=op.f("uq_user_auth_sessions_v2_user_id")),
    )
    op.create_index(
        op.f("ix_user_auth_sessions_v2_user_auth_sessions_v2_user_id"),
        "user_auth_sessions_v2",
        ["user_id"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO user_auth_sessions_v2 (id, user_id, active_sessions, created_at, updated_at)
        SELECT
            uas.user_id,
            uas.user_id,
            COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'session_id', uas.id::text,
                        'token_jti', uas.token_jti,
                        'token_hash', uas.token_hash,
                        'device_id', uas.device_id,
                        'device_name', uas.device_name,
                        'device_type', uas.device_type,
                        'user_agent', uas.user_agent,
                        'ip_address', uas.ip_address,
                        'issued_at', to_char(uas.issued_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
                        'expires_at', to_char(uas.expires_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
                        'last_seen_at', to_char(uas.last_seen_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
                        'created_at', to_char(uas.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
                        'updated_at', to_char(uas.updated_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
                    )
                    ORDER BY uas.last_seen_at DESC, uas.created_at DESC
                ),
                '[]'::jsonb
            ),
            MIN(uas.created_at),
            MAX(uas.updated_at)
        FROM user_auth_sessions AS uas
        GROUP BY uas.user_id
        """
    )

    op.drop_index(op.f("ix_user_auth_sessions_user_auth_sessions_user_id"), table_name="user_auth_sessions")
    op.drop_index(op.f("ix_user_auth_sessions_user_auth_sessions_token_jti"), table_name="user_auth_sessions")
    op.drop_index(op.f("ix_user_auth_sessions_user_auth_sessions_expires_at"), table_name="user_auth_sessions")
    op.drop_index(op.f("ix_user_auth_sessions_user_auth_sessions_device_id"), table_name="user_auth_sessions")
    op.drop_table("user_auth_sessions")
    op.rename_table("user_auth_sessions_v2", "user_auth_sessions")

    op.execute(
        "ALTER INDEX ix_user_auth_sessions_v2_user_auth_sessions_v2_user_id RENAME TO ix_user_auth_sessions_user_auth_sessions_user_id"
    )
    op.execute(
        "ALTER TABLE user_auth_sessions RENAME CONSTRAINT pk_user_auth_sessions_v2 TO pk_user_auth_sessions"
    )
    op.execute(
        "ALTER TABLE user_auth_sessions RENAME CONSTRAINT uq_user_auth_sessions_v2_user_id TO uq_user_auth_sessions_user_id"
    )
    op.execute(
        "ALTER TABLE user_auth_sessions RENAME CONSTRAINT fk_user_auth_sessions_v2_user_id_users TO fk_user_auth_sessions_user_id_users"
    )
    op.execute(
        "ALTER TABLE user_auth_sessions RENAME CONSTRAINT ck_user_auth_sessions_v2_active_sessions_array_check TO ck_user_auth_sessions_active_sessions_array_check"
    )
    op.alter_column("user_auth_sessions", "active_sessions", server_default=None)


def downgrade() -> None:
    op.create_table(
        "user_auth_sessions_legacy",
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
            name=op.f("ck_user_auth_sessions_legacy_user_auth_session_device_type_check"),
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name=op.f("ck_user_auth_sessions_legacy_user_auth_session_expiry_window_check"),
        ),
        sa.CheckConstraint(
            "length(trim(token_hash)) = 64",
            name=op.f("ck_user_auth_sessions_legacy_user_auth_session_token_hash_check"),
        ),
        sa.CheckConstraint(
            "length(trim(token_jti)) >= 1",
            name=op.f("ck_user_auth_sessions_legacy_user_auth_session_token_jti_check"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_auth_sessions_legacy_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_auth_sessions_legacy")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_auth_sessions_legacy_token_hash")),
        sa.UniqueConstraint("token_jti", name=op.f("uq_user_auth_sessions_legacy_token_jti")),
    )
    op.create_index(
        op.f("ix_user_auth_sessions_legacy_user_auth_sessions_legacy_device_id"),
        "user_auth_sessions_legacy",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_auth_sessions_legacy_user_auth_sessions_legacy_expires_at"),
        "user_auth_sessions_legacy",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_auth_sessions_legacy_user_auth_sessions_legacy_token_jti"),
        "user_auth_sessions_legacy",
        ["token_jti"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_auth_sessions_legacy_user_auth_sessions_legacy_user_id"),
        "user_auth_sessions_legacy",
        ["user_id"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO user_auth_sessions_legacy (
            id, user_id, token_jti, token_hash, device_id, device_name, device_type,
            user_agent, ip_address, issued_at, expires_at, last_seen_at, created_at, updated_at
        )
        SELECT
            (entry->>'session_id')::uuid,
            uas.user_id,
            entry->>'token_jti',
            entry->>'token_hash',
            NULLIF(entry->>'device_id', ''),
            NULLIF(entry->>'device_name', ''),
            NULLIF(entry->>'device_type', ''),
            NULLIF(entry->>'user_agent', ''),
            NULLIF(entry->>'ip_address', ''),
            (entry->>'issued_at')::timestamptz,
            (entry->>'expires_at')::timestamptz,
            (entry->>'last_seen_at')::timestamptz,
            (entry->>'created_at')::timestamptz,
            (entry->>'updated_at')::timestamptz
        FROM user_auth_sessions AS uas
        CROSS JOIN LATERAL jsonb_array_elements(uas.active_sessions) AS entry
        """
    )

    op.drop_index(op.f("ix_user_auth_sessions_user_auth_sessions_user_id"), table_name="user_auth_sessions")
    op.drop_table("user_auth_sessions")
    op.rename_table("user_auth_sessions_legacy", "user_auth_sessions")
    op.execute(
        "ALTER INDEX ix_user_auth_sessions_legacy_user_auth_sessions_legacy_device_id RENAME TO ix_user_auth_sessions_user_auth_sessions_device_id"
    )
    op.execute(
        "ALTER INDEX ix_user_auth_sessions_legacy_user_auth_sessions_legacy_expires_at RENAME TO ix_user_auth_sessions_user_auth_sessions_expires_at"
    )
    op.execute(
        "ALTER INDEX ix_user_auth_sessions_legacy_user_auth_sessions_legacy_token_jti RENAME TO ix_user_auth_sessions_user_auth_sessions_token_jti"
    )
    op.execute(
        "ALTER INDEX ix_user_auth_sessions_legacy_user_auth_sessions_legacy_user_id RENAME TO ix_user_auth_sessions_user_auth_sessions_user_id"
    )
    op.execute(
        "ALTER TABLE user_auth_sessions RENAME CONSTRAINT pk_user_auth_sessions_legacy TO pk_user_auth_sessions"
    )
    op.execute(
        "ALTER TABLE user_auth_sessions RENAME CONSTRAINT uq_user_auth_sessions_legacy_token_hash TO uq_user_auth_sessions_token_hash"
    )
    op.execute(
        "ALTER TABLE user_auth_sessions RENAME CONSTRAINT uq_user_auth_sessions_legacy_token_jti TO uq_user_auth_sessions_token_jti"
    )
    op.execute(
        "ALTER TABLE user_auth_sessions RENAME CONSTRAINT fk_user_auth_sessions_legacy_user_id_users TO fk_user_auth_sessions_user_id_users"
    )
    op.execute(
        "ALTER TABLE user_auth_sessions RENAME CONSTRAINT ck_user_auth_sessions_legacy_user_auth_session_device_type_check TO ck_user_auth_sessions_user_auth_session_device_type_check"
    )
    op.execute(
        "ALTER TABLE user_auth_sessions RENAME CONSTRAINT ck_user_auth_sessions_legacy_user_auth_session_expiry_window_check TO ck_user_auth_sessions_user_auth_session_expiry_window_check"
    )
    op.execute(
        "ALTER TABLE user_auth_sessions RENAME CONSTRAINT ck_user_auth_sessions_legacy_user_auth_session_token_hash_check TO ck_user_auth_sessions_user_auth_session_token_hash_check"
    )
    op.execute(
        "ALTER TABLE user_auth_sessions RENAME CONSTRAINT ck_user_auth_sessions_legacy_user_auth_session_token_jti_check TO ck_user_auth_sessions_user_auth_session_token_jti_check"
    )
