"""add tokens invalid before

Revision ID: eb78ce068e08
Revises: 5b4b0be02acd
Created: 2026-08-06 10:40:45.644770+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "eb78ce068e08"
down_revision: str | None = "5b4b0be02acd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the schema change."""
    op.add_column(
        "users", sa.Column("tokens_invalid_before", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Revert the schema change."""
    op.drop_column("users", "tokens_invalid_before")
