"""create users and refresh tokens

Revision ID: 2041be27b839
Revises:
Created: 2026-08-03 19:46:09.891363+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2041be27b839"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the schema change."""
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("phone_number", sa.String(length=16), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "suspended", name="user_status"),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "subscription_tier",
            sa.Enum("free", "premium", name="subscription_tier"),
            server_default="free",
            nullable=False,
        ),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "failed_login_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "phone_number IS NULL OR phone_number ~ '^\\+[1-9][0-9]{7,14}$'",
            name=op.f("ck_users_phone_number_is_e164"),
        ),
        sa.CheckConstraint(
            "failed_login_attempts >= 0", name=op.f("ck_users_failed_login_attempts_non_negative")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_deleted_at"), "users", ["deleted_at"], unique=False)
    op.create_index(
        "ix_users_email_active",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_users_phone_number_active",
        "users",
        ["phone_number"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND phone_number IS NOT NULL"),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.Uuid(), nullable=True),
        sa.Column("user_agent", sa.String(length=400), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_tokens.id"],
            name=op.f("fk_refresh_tokens_replaced_by_id_refresh_tokens"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
    )
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"], unique=False)
    op.create_index(
        "ix_refresh_tokens_user_id_active",
        "refresh_tokens",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    """Revert the schema change."""
    op.drop_index(
        "ix_refresh_tokens_user_id_active",
        table_name="refresh_tokens",
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index(
        "ix_users_phone_number_active",
        table_name="users",
        postgresql_where=sa.text("deleted_at IS NULL AND phone_number IS NOT NULL"),
    )
    op.drop_index(
        "ix_users_email_active", table_name="users", postgresql_where=sa.text("deleted_at IS NULL")
    )
    op.drop_index(op.f("ix_users_deleted_at"), table_name="users")
    op.drop_table("users")

    # Dropping a table leaves its enum types behind, so a downgrade followed by
    # an upgrade would fail with "type already exists" unless they go too.
    bind = op.get_bind()
    for enum_name in ("subscription_tier", "user_status"):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
