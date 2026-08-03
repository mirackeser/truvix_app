"""create copilot conversations and messages

Revision ID: 8d3d1e6462dd
Revises: cfab8d4356ff
Created: 2026-08-03 20:46:13.411511+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8d3d1e6462dd"
down_revision: str | None = "cfab8d4356ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the schema change."""
    op.create_table(
        "copilot_conversations",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_copilot_conversations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_copilot_conversations_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_copilot_conversations")),
    )
    op.create_index(
        "ix_copilot_conversations_user_recent",
        "copilot_conversations",
        ["user_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_copilot_conversations_vehicle_id", "copilot_conversations", ["vehicle_id"], unique=False
    )
    op.create_table(
        "copilot_messages",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role", sa.Enum("user", "assistant", name="copilot_message_role"), nullable=False
        ),
        sa.Column("content", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["copilot_conversations.id"],
            name=op.f("fk_copilot_messages_conversation_id_copilot_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_copilot_messages")),
    )
    op.create_index(
        "ix_copilot_messages_conversation_recent",
        "copilot_messages",
        ["conversation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Revert the schema change."""
    op.drop_index("ix_copilot_messages_conversation_recent", table_name="copilot_messages")
    op.drop_table("copilot_messages")
    op.drop_index("ix_copilot_conversations_vehicle_id", table_name="copilot_conversations")
    op.drop_index("ix_copilot_conversations_user_recent", table_name="copilot_conversations")
    op.drop_table("copilot_conversations")

    # The enum type must go with its table or a downgrade-then-upgrade fails.
    sa.Enum(name="copilot_message_role").drop(op.get_bind(), checkfirst=True)
