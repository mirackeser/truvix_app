"""Request and response models for the garage endpoints."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from truvix.modules.vehicles.models import (
    CITY_MAX_LENGTH,
    COLLECTION_NAME_MAX_LENGTH,
    COLOUR_MAX_LENGTH,
    MAKE_MAX_LENGTH,
    MODEL_MAX_LENGTH,
    NOTES_MAX_LENGTH,
    VARIANT_MAX_LENGTH,
    VIN_LENGTH,
    BodyType,
    Currency,
    FuelType,
    ListingSource,
    PriceSnapshot,
    PriceSource,
    SellerType,
    Transmission,
    Vehicle,
)
from truvix.shared.schemas import StrictRequest

# The earliest model year worth accepting from a used-car listing.
EARLIEST_MODEL_YEAR = 1950
# Manufacturers sell next year's models late in the current year.
MODEL_YEAR_LOOKAHEAD = 1

# No road vehicle credibly exceeds this; a larger figure is a typo or a fraud.
MAX_MILEAGE_KM = 3_000_000

MAX_PRICE = Decimal("999_999_999.99")
MIN_PRICE = Decimal("1")

# Turkish plates: two-digit province, one to three letters, two to five digits.
_PLATE_INPUT_PATTERN = re.compile(r"^\d{2}\s?[A-Za-z]{1,3}\s?\d{2,5}$")
# ISO 3779 excludes I, O and Q so they cannot be confused with 1 and 0.
_VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

_WHITESPACE = re.compile(r"\s+")


def _current_year() -> int:
    """The current calendar year in UTC."""
    return datetime.now(UTC).year


class GarageFilter(StrEnum):
    """Which slice of the garage a list request wants.

    These mirror the tabs on the garage screen. Membership is derived at query
    time rather than stored, so a vehicle appears under "price dropped" exactly
    when its history says so.
    """

    ALL = "all"
    FAVOURITES = "favourites"
    COMPARISON = "comparison"
    PRICE_DROPPED = "price_dropped"
    VIEWED_TODAY = "viewed_today"


class VehicleSort(StrEnum):
    """Ordering applied to a garage listing."""

    RECENTLY_ADDED = "recently_added"
    RECENTLY_VIEWED = "recently_viewed"
    PRICE_ASCENDING = "price_asc"
    PRICE_DESCENDING = "price_desc"


ModelYear = Annotated[int, Field(ge=EARLIEST_MODEL_YEAR)]
MileageKm = Annotated[int, Field(ge=0, le=MAX_MILEAGE_KM)]
Price = Annotated[Decimal, Field(ge=MIN_PRICE, le=MAX_PRICE, decimal_places=2)]


class _VehicleFields(StrictRequest):
    """Fields shared by the create and update payloads."""

    @field_validator("plate", check_fields=False)
    @classmethod
    def _normalise_plate(cls, value: str | None) -> str | None:
        """Validate and reduce a Turkish plate to its canonical form."""
        if value is None:
            return None
        if not _PLATE_INPUT_PATTERN.match(value):
            raise ValueError("Plate must look like '34 ABC 123'.")
        return _WHITESPACE.sub("", value).upper()

    @field_validator("vin", check_fields=False)
    @classmethod
    def _normalise_vin(cls, value: str | None) -> str | None:
        """Validate a vehicle identification number and uppercase it."""
        if value is None:
            return None
        candidate = _WHITESPACE.sub("", value).upper()
        if not _VIN_PATTERN.match(candidate):
            raise ValueError(f"VIN must be {VIN_LENGTH} characters and may not contain I, O or Q.")
        return candidate

    @field_validator("model_year", check_fields=False)
    @classmethod
    def _reject_implausible_year(cls, value: int) -> int:
        """Reject model years beyond what a manufacturer could have released."""
        ceiling = _current_year() + MODEL_YEAR_LOOKAHEAD
        if value > ceiling:
            raise ValueError(f"Model year cannot be later than {ceiling}.")
        return value


class VehicleCreateRequest(_VehicleFields):
    """Payload for saving a vehicle to the garage."""

    make: Annotated[str, Field(min_length=1, max_length=MAKE_MAX_LENGTH)]
    model: Annotated[str, Field(min_length=1, max_length=MODEL_MAX_LENGTH)]
    variant: Annotated[str, Field(max_length=VARIANT_MAX_LENGTH)] | None = None
    model_year: ModelYear
    mileage_km: MileageKm

    fuel_type: FuelType
    transmission: Transmission
    body_type: BodyType | None = None
    colour: Annotated[str, Field(max_length=COLOUR_MAX_LENGTH)] | None = None

    plate: str | None = None
    vin: str | None = None

    listing_source: ListingSource = ListingSource.MANUAL
    listing_url: HttpUrl | None = None
    seller_type: SellerType | None = None
    city: Annotated[str, Field(max_length=CITY_MAX_LENGTH)] | None = None

    asking_price: Price
    currency: Currency = Currency.TRY
    notes: Annotated[str, Field(max_length=NOTES_MAX_LENGTH)] | None = None


class VehicleUpdateRequest(_VehicleFields):
    """Payload for changing a saved vehicle.

    Every field is optional; only those present in the request body are applied,
    so a client can send a single changed attribute without having to resend the
    whole record and risk clobbering a concurrent edit.
    """

    make: Annotated[str, Field(min_length=1, max_length=MAKE_MAX_LENGTH)] | None = None
    model: Annotated[str, Field(min_length=1, max_length=MODEL_MAX_LENGTH)] | None = None
    variant: Annotated[str, Field(max_length=VARIANT_MAX_LENGTH)] | None = None
    model_year: ModelYear | None = None
    mileage_km: MileageKm | None = None

    fuel_type: FuelType | None = None
    transmission: Transmission | None = None
    body_type: BodyType | None = None
    colour: Annotated[str, Field(max_length=COLOUR_MAX_LENGTH)] | None = None

    plate: str | None = None
    vin: str | None = None

    listing_source: ListingSource | None = None
    listing_url: HttpUrl | None = None
    seller_type: SellerType | None = None
    city: Annotated[str, Field(max_length=CITY_MAX_LENGTH)] | None = None

    asking_price: Price | None = None
    currency: Currency | None = None
    notes: Annotated[str, Field(max_length=NOTES_MAX_LENGTH)] | None = None
    is_favourite: bool | None = None
    is_in_comparison: bool | None = None


class PriceUpdateRequest(StrictRequest):
    """Payload for recording a new observed price."""

    price: Price
    observed_at: datetime | None = Field(
        default=None,
        description="When the price was seen. Defaults to now. May not be in the future.",
    )

    @field_validator("observed_at")
    @classmethod
    def _reject_future_observations(cls, value: datetime | None) -> datetime | None:
        """Reject observations dated in the future."""
        if value is not None and value > datetime.now(UTC):
            raise ValueError("Observation time cannot be in the future.")
        return value


class PriceSnapshotResponse(BaseModel):
    """One recorded price observation."""

    model_config = ConfigDict(from_attributes=True)

    price: Decimal
    currency: Currency
    observed_at: datetime
    source: PriceSource

    @classmethod
    def from_snapshot(cls, snapshot: PriceSnapshot) -> Self:
        """Build the response from a persisted observation."""
        return cls(
            price=snapshot.price,
            currency=snapshot.currency,
            observed_at=snapshot.observed_at,
            source=snapshot.source,
        )


class PriceTrend(BaseModel):
    """How a vehicle's price moved over a window."""

    current_price: Decimal
    previous_price: Decimal | None
    absolute_change: Decimal | None
    percentage_change: Annotated[Decimal, Field(decimal_places=2)] | None
    window_days: int
    observation_count: int

    @property
    def has_dropped(self) -> bool:
        """Whether the price fell across the window."""
        return self.absolute_change is not None and self.absolute_change < 0


class VehicleResponse(BaseModel):
    """Full view of a saved vehicle."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    make: str
    model: str
    variant: str | None
    display_name: str
    model_year: int
    mileage_km: int

    fuel_type: FuelType
    transmission: Transmission
    body_type: BodyType | None
    colour: str | None

    plate: str | None
    vin: str | None

    listing_source: ListingSource
    listing_url: str | None
    seller_type: SellerType | None
    city: str | None

    asking_price: Decimal
    currency: Currency

    is_favourite: bool
    is_in_comparison: bool
    notes: str | None
    last_viewed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_vehicle(cls, vehicle: Vehicle) -> Self:
        """Build the response from a persisted vehicle."""
        return cls(
            id=vehicle.id,
            make=vehicle.make,
            model=vehicle.model,
            variant=vehicle.variant,
            display_name=vehicle.display_name,
            model_year=vehicle.model_year,
            mileage_km=vehicle.mileage_km,
            fuel_type=vehicle.fuel_type,
            transmission=vehicle.transmission,
            body_type=vehicle.body_type,
            colour=vehicle.colour,
            plate=vehicle.plate,
            vin=vehicle.vin,
            listing_source=vehicle.listing_source,
            listing_url=vehicle.listing_url,
            seller_type=vehicle.seller_type,
            city=vehicle.city,
            asking_price=vehicle.asking_price,
            currency=vehicle.currency,
            is_favourite=vehicle.is_favourite,
            is_in_comparison=vehicle.is_in_comparison,
            notes=vehicle.notes,
            last_viewed_at=vehicle.last_viewed_at,
            created_at=vehicle.created_at,
            updated_at=vehicle.updated_at,
        )


class VehicleSummaryResponse(BaseModel):
    """Compact view used by the garage list, carrying its price movement."""

    vehicle: VehicleResponse
    price_trend: PriceTrend | None


class GarageStatsResponse(BaseModel):
    """Counts backing the garage screen's tabs and header."""

    total: int
    favourites: int
    in_comparison: int
    price_dropped: int
    viewed_today: int


class PriceHistoryPoint(BaseModel):
    """One point on the price chart."""

    observed_on: date
    price: Decimal


class PriceHistoryResponse(BaseModel):
    """The series drawn by the price chart, plus its summary figures."""

    vehicle_id: uuid.UUID
    currency: Currency
    window_days: int
    points: list[PriceHistoryPoint]
    trend: PriceTrend | None


class CollectionCreateRequest(StrictRequest):
    """Payload for creating a collection."""

    name: Annotated[str, Field(min_length=1, max_length=COLLECTION_NAME_MAX_LENGTH)]


class CollectionResponse(BaseModel):
    """A collection and how many vehicles it holds."""

    id: uuid.UUID
    name: str
    vehicle_count: int
    created_at: datetime
