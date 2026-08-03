"""create vehicles price snapshots and collections

Revision ID: d4f167d2a057
Revises: 2041be27b839
Created: 2026-08-03 20:11:05.700313+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4f167d2a057"
down_revision: str | None = "2041be27b839"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the schema change."""
    op.create_table(
        "collections",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
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
            ["user_id"], ["users.id"], name=op.f("fk_collections_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collections")),
        sa.UniqueConstraint("user_id", "name", name="uq_collections_user_id_name"),
    )
    op.create_index("ix_collections_user_id", "collections", ["user_id"], unique=False)
    op.create_table(
        "vehicles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("make", sa.String(length=60), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("variant", sa.String(length=80), nullable=True),
        sa.Column("model_year", sa.Integer(), nullable=False),
        sa.Column("mileage_km", sa.Integer(), nullable=False),
        sa.Column(
            "fuel_type",
            sa.Enum("petrol", "diesel", "lpg", "hybrid", "electric", name="fuel_type"),
            nullable=False,
        ),
        sa.Column(
            "transmission",
            sa.Enum("manual", "automatic", "semi_automatic", name="transmission"),
            nullable=False,
        ),
        sa.Column(
            "body_type",
            sa.Enum(
                "sedan",
                "hatchback",
                "suv",
                "coupe",
                "station_wagon",
                "mpv",
                "pickup",
                "convertible",
                name="body_type",
            ),
            nullable=True,
        ),
        sa.Column("colour", sa.String(length=40), nullable=True),
        sa.Column("plate", sa.String(length=12), nullable=True),
        sa.Column("vin", sa.String(length=17), nullable=True),
        sa.Column(
            "listing_source",
            sa.Enum("manual", "sahibinden", "arabam", "letgo", "other", name="listing_source"),
            server_default="manual",
            nullable=False,
        ),
        sa.Column("listing_url", sa.String(length=2048), nullable=True),
        sa.Column("seller_type", sa.Enum("owner", "dealer", name="seller_type"), nullable=True),
        sa.Column("city", sa.String(length=60), nullable=True),
        sa.Column("asking_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "currency",
            sa.Enum("TRY", "USD", "EUR", name="currency"),
            server_default="TRY",
            nullable=False,
        ),
        sa.Column("is_favourite", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "is_in_comparison", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("asking_price > 0", name=op.f("ck_vehicles_asking_price_positive")),
        sa.CheckConstraint("mileage_km >= 0", name=op.f("ck_vehicles_mileage_non_negative")),
        sa.CheckConstraint(
            "model_year BETWEEN 1900 AND 2100", name=op.f("ck_vehicles_model_year_in_range")
        ),
        sa.CheckConstraint(
            "vin IS NULL OR char_length(vin) = 17", name=op.f("ck_vehicles_vin_has_iso_length")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_vehicles_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vehicles")),
    )
    op.create_index(op.f("ix_vehicles_deleted_at"), "vehicles", ["deleted_at"], unique=False)
    op.create_index(
        "ix_vehicles_owner_comparison",
        "vehicles",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL AND is_in_comparison"),
    )
    op.create_index(
        "ix_vehicles_owner_favourite",
        "vehicles",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL AND is_favourite"),
    )
    op.create_index(
        "ix_vehicles_owner_last_viewed",
        "vehicles",
        ["user_id", sa.literal_column("last_viewed_at DESC")],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL AND last_viewed_at IS NOT NULL"),
    )
    op.create_index(
        "ix_vehicles_owner_recent",
        "vehicles",
        ["user_id", sa.literal_column("created_at DESC")],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "collection_items",
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
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
            ["collection_id"],
            ["collections.id"],
            name=op.f("fk_collection_items_collection_id_collections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_collection_items_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("collection_id", "vehicle_id", name=op.f("pk_collection_items")),
    )
    op.create_index(
        "ix_collection_items_vehicle_id", "collection_items", ["vehicle_id"], unique=False
    )
    op.create_table(
        "price_snapshots",
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.Enum("TRY", "USD", "EUR", name="currency"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source",
            sa.Enum("user_reported", "listing_import", name="price_source"),
            server_default="user_reported",
            nullable=False,
        ),
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
        sa.CheckConstraint("price > 0", name=op.f("ck_price_snapshots_price_positive")),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_price_snapshots_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_snapshots")),
    )
    op.create_index(
        "ix_price_snapshots_vehicle_observed",
        "price_snapshots",
        ["vehicle_id", sa.literal_column("observed_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Revert the schema change."""
    op.drop_index("ix_price_snapshots_vehicle_observed", table_name="price_snapshots")
    op.drop_table("price_snapshots")
    op.drop_index("ix_collection_items_vehicle_id", table_name="collection_items")
    op.drop_table("collection_items")
    op.drop_index(
        "ix_vehicles_owner_recent",
        table_name="vehicles",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        "ix_vehicles_owner_last_viewed",
        table_name="vehicles",
        postgresql_where=sa.text("deleted_at IS NULL AND last_viewed_at IS NOT NULL"),
    )
    op.drop_index(
        "ix_vehicles_owner_favourite",
        table_name="vehicles",
        postgresql_where=sa.text("deleted_at IS NULL AND is_favourite"),
    )
    op.drop_index(
        "ix_vehicles_owner_comparison",
        table_name="vehicles",
        postgresql_where=sa.text("deleted_at IS NULL AND is_in_comparison"),
    )
    op.drop_index(op.f("ix_vehicles_deleted_at"), table_name="vehicles")
    op.drop_table("vehicles")
    op.drop_index("ix_collections_user_id", table_name="collections")
    op.drop_table("collections")

    # Dropping the tables leaves their enum types behind, so a downgrade
    # followed by an upgrade would fail on "type already exists".
    bind = op.get_bind()
    for enum_name in (
        "price_source",
        "currency",
        "seller_type",
        "listing_source",
        "body_type",
        "transmission",
        "fuel_type",
    ):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
