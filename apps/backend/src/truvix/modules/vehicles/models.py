"""Persistence models for garage vehicles, price history and collections.

A vehicle row belongs to exactly one user: it represents the specific car that
person is evaluating, not a shared catalogue entry. Two users looking at the
same listing therefore own two independent rows. That keeps the model free of
identity-matching guesswork — plates and VINs are frequently absent from
listings — and it means a user's evaluation notes and price history can never
leak across accounts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from truvix.shared.database import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    pg_enum,
)

if TYPE_CHECKING:
    from truvix.modules.users.models import User

MAKE_MAX_LENGTH = 60
MODEL_MAX_LENGTH = 80
VARIANT_MAX_LENGTH = 80
COLOUR_MAX_LENGTH = 40
CITY_MAX_LENGTH = 60
COLLECTION_NAME_MAX_LENGTH = 60
LISTING_URL_MAX_LENGTH = 2048
NOTES_MAX_LENGTH = 2000

# Turkish plates normalise to digits and uppercase letters with spaces removed.
PLATE_MAX_LENGTH = 12
# ISO 3779 fixes the vehicle identification number at seventeen characters.
VIN_LENGTH = 17

# Widest plausible range for a road vehicle; tighter limits live in the schemas
# so the database constraint does not need editing every January.
MIN_MODEL_YEAR = 1900
MAX_MODEL_YEAR = 2100

# Prices are held to the kurus. Twelve digits covers any road vehicle price in
# lira with room to spare, and Numeric avoids the rounding drift of floats.
PRICE_PRECISION = 12
PRICE_SCALE = 2


class FuelType(StrEnum):
    """Energy source the vehicle runs on."""

    PETROL = "petrol"
    DIESEL = "diesel"
    LPG = "lpg"
    HYBRID = "hybrid"
    ELECTRIC = "electric"


class Transmission(StrEnum):
    """Gearbox type."""

    MANUAL = "manual"
    AUTOMATIC = "automatic"
    SEMI_AUTOMATIC = "semi_automatic"


class BodyType(StrEnum):
    """Body style."""

    SEDAN = "sedan"
    HATCHBACK = "hatchback"
    SUV = "suv"
    COUPE = "coupe"
    STATION_WAGON = "station_wagon"
    MPV = "mpv"
    PICKUP = "pickup"
    CONVERTIBLE = "convertible"


class ListingSource(StrEnum):
    """Where the vehicle's details came from."""

    MANUAL = "manual"
    SAHIBINDEN = "sahibinden"
    ARABAM = "arabam"
    LETGO = "letgo"
    OTHER = "other"


class SellerType(StrEnum):
    """Who is offering the vehicle."""

    OWNER = "owner"
    DEALER = "dealer"


class Currency(StrEnum):
    """Currency a price is denominated in."""

    TRY = "TRY"
    USD = "USD"
    EUR = "EUR"


class PriceSource(StrEnum):
    """How a price observation was obtained."""

    USER_REPORTED = "user_reported"
    LISTING_IMPORT = "listing_import"


# Enum types are instantiated once and shared by every column that uses them.
# Building a second instance for the same PostgreSQL type name would make
# schema creation try to CREATE TYPE twice.
_FUEL_TYPE = pg_enum(FuelType, name="fuel_type")
_TRANSMISSION = pg_enum(Transmission, name="transmission")
_BODY_TYPE = pg_enum(BodyType, name="body_type")
_LISTING_SOURCE = pg_enum(ListingSource, name="listing_source")
_SELLER_TYPE = pg_enum(SellerType, name="seller_type")
_CURRENCY = pg_enum(Currency, name="currency")
_PRICE_SOURCE = pg_enum(PriceSource, name="price_source")


class Vehicle(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A vehicle saved to a user's garage."""

    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint(
            f"model_year BETWEEN {MIN_MODEL_YEAR} AND {MAX_MODEL_YEAR}",
            name="model_year_in_range",
        ),
        CheckConstraint("mileage_km >= 0", name="mileage_non_negative"),
        CheckConstraint("asking_price > 0", name="asking_price_positive"),
        CheckConstraint(
            f"vin IS NULL OR char_length(vin) = {VIN_LENGTH}",
            name="vin_has_iso_length",
        ),
        # The garage list is always scoped to one owner and ordered by recency.
        Index(
            "ix_vehicles_owner_recent",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Serves the "Favoriler" and "Karşılaştırılacaklar" collections.
        Index(
            "ix_vehicles_owner_favourite",
            "user_id",
            postgresql_where=text("deleted_at IS NULL AND is_favourite"),
        ),
        Index(
            "ix_vehicles_owner_comparison",
            "user_id",
            postgresql_where=text("deleted_at IS NULL AND is_in_comparison"),
        ),
        # Serves "Bugün Bakılanlar".
        Index(
            "ix_vehicles_owner_last_viewed",
            "user_id",
            text("last_viewed_at DESC"),
            postgresql_where=text("deleted_at IS NULL AND last_viewed_at IS NOT NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    make: Mapped[str] = mapped_column(String(MAKE_MAX_LENGTH), nullable=False)
    model: Mapped[str] = mapped_column(String(MODEL_MAX_LENGTH), nullable=False)
    variant: Mapped[str | None] = mapped_column(String(VARIANT_MAX_LENGTH))
    model_year: Mapped[int] = mapped_column(Integer, nullable=False)
    mileage_km: Mapped[int] = mapped_column(Integer, nullable=False)

    fuel_type: Mapped[FuelType] = mapped_column(_FUEL_TYPE, nullable=False)
    transmission: Mapped[Transmission] = mapped_column(_TRANSMISSION, nullable=False)
    body_type: Mapped[BodyType | None] = mapped_column(_BODY_TYPE)
    colour: Mapped[str | None] = mapped_column(String(COLOUR_MAX_LENGTH))

    plate: Mapped[str | None] = mapped_column(String(PLATE_MAX_LENGTH))
    vin: Mapped[str | None] = mapped_column(String(VIN_LENGTH))

    listing_source: Mapped[ListingSource] = mapped_column(
        _LISTING_SOURCE,
        nullable=False,
        default=ListingSource.MANUAL,
        server_default=ListingSource.MANUAL.value,
    )
    listing_url: Mapped[str | None] = mapped_column(String(LISTING_URL_MAX_LENGTH))
    seller_type: Mapped[SellerType | None] = mapped_column(_SELLER_TYPE)
    city: Mapped[str | None] = mapped_column(String(CITY_MAX_LENGTH))

    asking_price: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False
    )
    currency: Mapped[Currency] = mapped_column(
        _CURRENCY,
        nullable=False,
        default=Currency.TRY,
        server_default=Currency.TRY.value,
    )

    is_favourite: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    is_in_comparison: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User] = relationship()
    price_snapshots: Mapped[list[PriceSnapshot]] = relationship(
        back_populates="vehicle",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PriceSnapshot.observed_at.desc()",
    )

    @property
    def display_name(self) -> str:
        """Human-readable label, matching how the garage list renders a card."""
        parts = [self.make, self.model]
        if self.variant:
            parts.append(self.variant)
        return " ".join(parts)

    def __repr__(self) -> str:
        return f"Vehicle(id={self.id!r}, make={self.make!r}, model={self.model!r})"


class PriceSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One observation of a vehicle's asking price at a point in time.

    Snapshots are append-only. Correcting a mistaken price means recording a new
    observation, never editing an old one, so the history a user sees on the
    price chart is always the history that actually happened.
    """

    __tablename__ = "price_snapshots"
    __table_args__ = (
        CheckConstraint("price > 0", name="price_positive"),
        # Every read walks one vehicle's history newest-first, whether drawing
        # the chart or computing the change over a window.
        Index("ix_price_snapshots_vehicle_observed", "vehicle_id", text("observed_at DESC")),
    )

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False)
    currency: Mapped[Currency] = mapped_column(_CURRENCY, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[PriceSource] = mapped_column(
        _PRICE_SOURCE,
        nullable=False,
        default=PriceSource.USER_REPORTED,
        server_default=PriceSource.USER_REPORTED.value,
    )

    vehicle: Mapped[Vehicle] = relationship(back_populates="price_snapshots")

    def __repr__(self) -> str:
        return f"PriceSnapshot(vehicle_id={self.vehicle_id!r}, price={self.price!r})"


class Collection(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A user-created grouping of vehicles.

    Only groupings whose membership a user chooses are stored. The garage's
    other tabs — vehicles viewed today, vehicles whose price fell — are derived
    from the data at query time, because storing them would mean maintaining a
    cache that can silently disagree with the truth.
    """

    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_collections_user_id_name"),
        Index("ix_collections_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(COLLECTION_NAME_MAX_LENGTH), nullable=False)

    items: Mapped[list[CollectionItem]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"Collection(id={self.id!r}, name={self.name!r})"


class CollectionItem(Base, TimestampMixin):
    """Membership of one vehicle in one collection."""

    __tablename__ = "collection_items"
    __table_args__ = (Index("ix_collection_items_vehicle_id", "vehicle_id"),)

    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        primary_key=True,
    )

    collection: Mapped[Collection] = relationship(back_populates="items")
    vehicle: Mapped[Vehicle] = relationship()

    def __repr__(self) -> str:
        return (
            f"CollectionItem(collection_id={self.collection_id!r}, vehicle_id={self.vehicle_id!r})"
        )
