"""create entitlements

Revision ID: 95dbe3e6bb73
Revises: 603b2655cd7a
Created: 2026-08-05 09:53:38.742777+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "95dbe3e6bb73"
down_revision: str | None = "603b2655cd7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENTITLEMENT_STATUS = sa.Enum(
    "active",
    "expired",
    "in_grace_period",
    "in_billing_retry",
    "revoked",
    name="entitlement_status",
)
_STORE_ENVIRONMENT = sa.Enum("sandbox", "production", name="store_environment")


def upgrade() -> None:
    """Apply the schema change."""
    # The types are created by the table below; creating them here as well
    # would fail, since one CREATE TYPE per name is all PostgreSQL allows.
    op.create_table(
        "entitlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.String(length=120), nullable=False),
        sa.Column("original_transaction_id", sa.String(length=64), nullable=False),
        sa.Column("latest_transaction_id", sa.String(length=64), nullable=False),
        sa.Column("status", _ENTITLEMENT_STATUS, nullable=False),
        sa.Column("environment", _STORE_ENVIRONMENT, nullable=False),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_entitlements_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entitlements")),
        # Apple's original transaction id identifies a subscription for its whole
        # life. Unique here is what stops one purchase entitling two accounts.
        sa.UniqueConstraint(
            "original_transaction_id", name="uq_entitlements_original_transaction_id"
        ),
    )
    op.create_index("ix_entitlements_expires_at", "entitlements", ["expires_at"], unique=False)
    op.create_index("ix_entitlements_user_id", "entitlements", ["user_id"], unique=False)


def downgrade() -> None:
    """Revert the schema change."""
    op.drop_index("ix_entitlements_user_id", table_name="entitlements")
    op.drop_index("ix_entitlements_expires_at", table_name="entitlements")
    op.drop_table("entitlements")

    # The enum types must go with their table or a downgrade-then-upgrade fails.
    bind = op.get_bind()
    _STORE_ENVIRONMENT.drop(bind, checkfirst=True)
    _ENTITLEMENT_STATUS.drop(bind, checkfirst=True)
