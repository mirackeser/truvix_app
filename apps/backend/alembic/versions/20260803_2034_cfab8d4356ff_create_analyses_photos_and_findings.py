"""create analyses photos and findings

Revision ID: cfab8d4356ff
Revises: d4f167d2a057
Created: 2026-08-03 20:34:04.823589+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cfab8d4356ff"
down_revision: str | None = "d4f167d2a057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the schema change."""
    op.create_table(
        "vehicle_analyses",
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "processing", "completed", "failed", name="analysis_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("trust_score", sa.Integer(), nullable=True),
        sa.Column("risk_level", sa.Enum("low", "medium", "high", name="risk_level"), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "(status = 'completed') = (trust_score IS NOT NULL)",
            name=op.f("ck_vehicle_analyses_score_present_iff_completed"),
        ),
        sa.CheckConstraint(
            "(status = 'failed') = (failure_reason IS NOT NULL)",
            name=op.f("ck_vehicle_analyses_failure_reason_present_iff_failed"),
        ),
        sa.CheckConstraint(
            "trust_score IS NULL OR trust_score BETWEEN 0 AND 100",
            name=op.f("ck_vehicle_analyses_trust_score_in_range"),
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_vehicle_analyses_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vehicle_analyses")),
    )
    op.create_index(
        "ix_vehicle_analyses_vehicle_recent",
        "vehicle_analyses",
        ["vehicle_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_table(
        "analysis_photos",
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "exterior",
                "interior",
                "engine",
                "dashboard",
                "damage",
                "document",
                "other",
                name="photo_kind",
            ),
            server_default="other",
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
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
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_analysis_photos_size_positive")),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["vehicle_analyses.id"],
            name=op.f("fk_analysis_photos_analysis_id_vehicle_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_photos")),
    )
    op.create_index(
        "ix_analysis_photos_analysis_id", "analysis_photos", ["analysis_id"], unique=False
    )
    op.create_table(
        "risk_findings",
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "mileage",
                "age",
                "damage",
                "maintenance",
                "price",
                "documentation",
                "general",
                name="finding_category",
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum("positive", "info", "warning", "critical", name="finding_severity"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("detail", sa.String(length=1000), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
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
            ["analysis_id"],
            ["vehicle_analyses.id"],
            name=op.f("fk_risk_findings_analysis_id_vehicle_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_findings")),
    )
    op.create_index("ix_risk_findings_analysis_id", "risk_findings", ["analysis_id"], unique=False)


def downgrade() -> None:
    """Revert the schema change."""
    op.drop_index("ix_risk_findings_analysis_id", table_name="risk_findings")
    op.drop_table("risk_findings")
    op.drop_index("ix_analysis_photos_analysis_id", table_name="analysis_photos")
    op.drop_table("analysis_photos")
    op.drop_index("ix_vehicle_analyses_vehicle_recent", table_name="vehicle_analyses")
    op.drop_table("vehicle_analyses")

    # Enum types must go with their tables or a downgrade-then-upgrade fails
    # on "type already exists".
    bind = op.get_bind()
    for enum_name in (
        "finding_category",
        "finding_severity",
        "photo_kind",
        "risk_level",
        "analysis_status",
    ):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
