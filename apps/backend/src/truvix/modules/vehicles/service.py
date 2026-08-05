"""Garage business logic: saved vehicles, price tracking and collections."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from truvix.modules.users.models import SubscriptionTier
from truvix.modules.vehicles.models import (
    Collection,
    CollectionItem,
    PriceSnapshot,
    PriceSource,
    Vehicle,
)
from truvix.modules.vehicles.repository import (
    CollectionRepository,
    PriceMovement,
    VehicleRepository,
)
from truvix.modules.vehicles.schemas import (
    CollectionResponse,
    GarageFilter,
    GarageStatsResponse,
    PriceHistoryPoint,
    PriceHistoryResponse,
    PriceTrend,
    VehicleCreateRequest,
    VehicleResponse,
    VehicleSort,
    VehicleSummaryResponse,
    VehicleUpdateRequest,
)
from truvix.shared.errors import ConflictError, NotFoundError
from truvix.shared.events import EventBus, PriceDropped
from truvix.shared.logging import get_logger
from truvix.shared.pagination import Page, PageParams
from truvix.shared.quota import QuotaService

_logger = get_logger(__name__)

# Truvix serves the Turkish market, so "today" and "this week" mean today and
# this week in Istanbul, not in UTC. Without this a user checking a car at
# 02:00 local time would see it filed under yesterday.
APP_TIMEZONE = ZoneInfo("Europe/Istanbul")

# Matches the garage screen's default price comparison window.
DEFAULT_PRICE_WINDOW_DAYS = 30
MAX_PRICE_WINDOW_DAYS = 365

_PERCENT = Decimal(100)
_PERCENT_QUANTUM = Decimal("0.01")

# How many collections one account may create, to bound per-user storage.
MAX_COLLECTIONS_PER_USER = 50


def local_day_start(*, now: datetime | None = None) -> datetime:
    """Return the start of the current day in the application's timezone.

    Args:
        now: The current time. Defaults to the real clock; supplied by tests.
    """
    moment = (now or datetime.now(UTC)).astimezone(APP_TIMEZONE)
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


class VehicleService:
    """Manages a user's garage."""

    def __init__(
        self,
        *,
        vehicles: VehicleRepository,
        collections: CollectionRepository,
        events: EventBus,
        quota: QuotaService,
    ) -> None:
        """Initialise the service.

        Args:
            vehicles: Access to vehicle and price records.
            collections: Access to collection records.
            events: Request-scoped bus for domain events.
            quota: The account's consumption ceilings.
        """
        self._vehicles = vehicles
        self._collections = collections
        self._events = events
        self._quota = quota

    async def create(
        self,
        *,
        owner_id: uuid.UUID,
        payload: VehicleCreateRequest,
        tier: SubscriptionTier,
    ) -> Vehicle:
        """Save a vehicle to the owner's garage.

        The asking price is also recorded as the first price observation, so a
        vehicle has a price history from the moment it is created rather than
        only after its price first changes.

        Args:
            owner_id: The account saving the vehicle.
            payload: Validated vehicle details.
            tier: The account's plan, which sets its garage ceiling.

        Returns:
            The saved vehicle.

        Raises:
            QuotaExceededError: If the garage is already at its ceiling.
        """
        counts = await self._vehicles.counts_for_owner(
            owner_id=owner_id, day_start=local_day_start()
        )
        self._quota.assert_vehicle_allowed(current_count=counts.total, tier=tier)

        vehicle = Vehicle(
            user_id=owner_id,
            make=payload.make,
            model=payload.model,
            variant=payload.variant,
            model_year=payload.model_year,
            mileage_km=payload.mileage_km,
            fuel_type=payload.fuel_type,
            transmission=payload.transmission,
            body_type=payload.body_type,
            colour=payload.colour,
            plate=payload.plate,
            vin=payload.vin,
            listing_source=payload.listing_source,
            listing_url=str(payload.listing_url) if payload.listing_url else None,
            seller_type=payload.seller_type,
            city=payload.city,
            asking_price=payload.asking_price,
            currency=payload.currency,
            notes=payload.notes,
        )
        self._vehicles.add(vehicle)
        await self._vehicles.flush()

        self._vehicles.add_price_snapshot(
            PriceSnapshot(
                vehicle_id=vehicle.id,
                price=payload.asking_price,
                currency=payload.currency,
                observed_at=datetime.now(UTC),
                source=PriceSource.USER_REPORTED,
            )
        )
        await self._vehicles.flush()

        _logger.info("vehicle_saved", vehicle_id=str(vehicle.id), owner_id=str(owner_id))
        return vehicle

    async def get(self, *, owner_id: uuid.UUID, vehicle_id: uuid.UUID) -> Vehicle:
        """Fetch one of the owner's vehicles and mark it as viewed.

        Args:
            owner_id: The account the vehicle must belong to.
            vehicle_id: The vehicle to fetch.

        Returns:
            The vehicle.

        Raises:
            NotFoundError: If no live vehicle with that id belongs to the owner.
        """
        vehicle = await self._require(owner_id=owner_id, vehicle_id=vehicle_id)
        vehicle.last_viewed_at = datetime.now(UTC)
        await self._vehicles.flush()
        return vehicle

    async def update(
        self, *, owner_id: uuid.UUID, vehicle_id: uuid.UUID, payload: VehicleUpdateRequest
    ) -> Vehicle:
        """Apply a partial update to one of the owner's vehicles.

        Changing the asking price also records a price observation, keeping the
        chart consistent with the value shown on the card.

        Args:
            owner_id: The account the vehicle must belong to.
            vehicle_id: The vehicle to change.
            payload: The fields to change.

        Returns:
            The updated vehicle.

        Raises:
            NotFoundError: If no live vehicle with that id belongs to the owner.
        """
        vehicle = await self._require(owner_id=owner_id, vehicle_id=vehicle_id)
        changes = payload.model_dump(exclude_unset=True)

        if "listing_url" in changes and changes["listing_url"] is not None:
            changes["listing_url"] = str(changes["listing_url"])

        previous_price = vehicle.asking_price
        new_price = changes.get("asking_price")
        price_changed = new_price is not None and new_price != previous_price

        for field, value in changes.items():
            setattr(vehicle, field, value)

        if price_changed and vehicle.asking_price < previous_price:
            self._events.publish(
                PriceDropped(
                    user_id=owner_id,
                    vehicle_id=vehicle.id,
                    vehicle_name=vehicle.display_name,
                    previous_price=previous_price,
                    new_price=vehicle.asking_price,
                )
            )

        if price_changed:
            self._vehicles.add_price_snapshot(
                PriceSnapshot(
                    vehicle_id=vehicle.id,
                    price=vehicle.asking_price,
                    currency=vehicle.currency,
                    observed_at=datetime.now(UTC),
                    source=PriceSource.USER_REPORTED,
                )
            )

        await self._vehicles.flush()
        _logger.info(
            "vehicle_updated",
            vehicle_id=str(vehicle.id),
            fields=sorted(changes),
            price_changed=price_changed,
        )
        return vehicle

    async def delete(self, *, owner_id: uuid.UUID, vehicle_id: uuid.UUID) -> None:
        """Remove a vehicle from the owner's garage.

        The row is soft-deleted so an accidental removal can be recovered and
        so the price history it accumulated is not destroyed.

        Args:
            owner_id: The account the vehicle must belong to.
            vehicle_id: The vehicle to remove.

        Raises:
            NotFoundError: If no live vehicle with that id belongs to the owner.
        """
        vehicle = await self._require(owner_id=owner_id, vehicle_id=vehicle_id)
        vehicle.deleted_at = datetime.now(UTC)
        await self._vehicles.flush()
        _logger.info("vehicle_deleted", vehicle_id=str(vehicle.id), owner_id=str(owner_id))

    async def record_price(
        self,
        *,
        owner_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        price: Decimal,
        observed_at: datetime | None,
    ) -> PriceSnapshot:
        """Record a newly observed price for one of the owner's vehicles.

        Args:
            owner_id: The account the vehicle must belong to.
            vehicle_id: The vehicle the observation belongs to.
            price: The observed price.
            observed_at: When it was seen. Defaults to now.

        Returns:
            The recorded observation.

        Raises:
            NotFoundError: If no live vehicle with that id belongs to the owner.
        """
        vehicle = await self._require(owner_id=owner_id, vehicle_id=vehicle_id)
        previous_price = vehicle.asking_price

        snapshot = PriceSnapshot(
            vehicle_id=vehicle.id,
            price=price,
            currency=vehicle.currency,
            observed_at=observed_at or datetime.now(UTC),
            source=PriceSource.USER_REPORTED,
        )
        self._vehicles.add_price_snapshot(snapshot)

        if price < previous_price:
            self._events.publish(
                PriceDropped(
                    user_id=owner_id,
                    vehicle_id=vehicle.id,
                    vehicle_name=vehicle.display_name,
                    previous_price=previous_price,
                    new_price=price,
                )
            )

        # The card always shows the most recent observation, so the vehicle's
        # asking price follows it rather than drifting out of step.
        vehicle.asking_price = price
        await self._vehicles.flush()

        _logger.info("price_recorded", vehicle_id=str(vehicle.id), price=str(price))
        return snapshot

    async def list_garage(
        self,
        *,
        owner_id: uuid.UUID,
        garage_filter: GarageFilter,
        sort: VehicleSort,
        params: PageParams,
        window_days: int = DEFAULT_PRICE_WINDOW_DAYS,
    ) -> Page[VehicleSummaryResponse]:
        """List a page of the owner's garage with each card's price movement.

        Args:
            owner_id: The account whose garage to list.
            garage_filter: Which tab of the garage to return.
            sort: Ordering to apply.
            params: Pagination parameters.
            window_days: Window used to compute price movement.

        Returns:
            A page of vehicle summaries.
        """
        window_start = self._window_start(window_days)
        vehicles, total = await self._vehicles.list_for_owner(
            owner_id=owner_id,
            garage_filter=garage_filter,
            sort=sort,
            params=params,
            price_window_start=window_start,
            day_start=local_day_start(),
        )

        movements = await self._vehicles.price_movements(
            vehicle_ids=[vehicle.id for vehicle in vehicles], since=window_start
        )
        items = [
            VehicleSummaryResponse(
                vehicle=VehicleResponse.from_vehicle(vehicle),
                price_trend=_build_trend(movements.get(vehicle.id), window_days=window_days),
            )
            for vehicle in vehicles
        ]
        return Page[VehicleSummaryResponse].create(items=items, total=total, params=params)

    async def garage_stats(
        self, *, owner_id: uuid.UUID, window_days: int = DEFAULT_PRICE_WINDOW_DAYS
    ) -> GarageStatsResponse:
        """Count the owner's vehicles per garage tab.

        Args:
            owner_id: The account whose garage to summarise.
            window_days: Window used to decide whether a price dropped.
        """
        counts = await self._vehicles.counts_for_owner(
            owner_id=owner_id, day_start=local_day_start()
        )
        dropped = await self._vehicles.count_with_dropped_price(
            owner_id=owner_id, price_window_start=self._window_start(window_days)
        )
        return GarageStatsResponse(
            total=counts.total,
            favourites=counts.favourites,
            in_comparison=counts.in_comparison,
            price_dropped=dropped,
            viewed_today=counts.viewed_today,
        )

    async def price_history(
        self,
        *,
        owner_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        window_days: int = DEFAULT_PRICE_WINDOW_DAYS,
    ) -> PriceHistoryResponse:
        """Build the price chart series for one of the owner's vehicles.

        Args:
            owner_id: The account the vehicle must belong to.
            vehicle_id: The vehicle whose history to read.
            window_days: How far back to read.

        Returns:
            The chart points together with the summary trend.

        Raises:
            NotFoundError: If no live vehicle with that id belongs to the owner.
        """
        vehicle = await self._require(owner_id=owner_id, vehicle_id=vehicle_id)
        window_start = self._window_start(window_days)

        snapshots = await self._vehicles.price_history(vehicle_id=vehicle.id, since=window_start)
        movements = await self._vehicles.price_movements(
            vehicle_ids=[vehicle.id], since=window_start
        )

        return PriceHistoryResponse(
            vehicle_id=vehicle.id,
            currency=vehicle.currency,
            window_days=window_days,
            points=_collapse_to_daily_points(snapshots),
            trend=_build_trend(movements.get(vehicle.id), window_days=window_days),
        )

    async def create_collection(self, *, owner_id: uuid.UUID, name: str) -> Collection:
        """Create a collection for the owner.

        Args:
            owner_id: The account creating the collection.
            name: The collection's name, unique within the account.

        Returns:
            The created collection.

        Raises:
            ConflictError: If the name is taken or the account is at its limit.
        """
        if await self._collections.name_is_taken(owner_id=owner_id, name=name):
            raise ConflictError("A collection with this name already exists.")

        existing = await self._collections.list_for_owner(owner_id=owner_id)
        if len(existing) >= MAX_COLLECTIONS_PER_USER:
            raise ConflictError(
                f"An account may hold at most {MAX_COLLECTIONS_PER_USER} collections."
            )

        collection = Collection(user_id=owner_id, name=name)
        self._collections.add(collection)
        await self._collections.flush()
        _logger.info("collection_created", collection_id=str(collection.id))
        return collection

    async def list_collections(self, *, owner_id: uuid.UUID) -> list[CollectionResponse]:
        """List the owner's collections with their sizes.

        Args:
            owner_id: The account whose collections to list.
        """
        rows = await self._collections.list_for_owner(owner_id=owner_id)
        return [
            CollectionResponse(
                id=collection.id,
                name=collection.name,
                vehicle_count=count,
                created_at=collection.created_at,
            )
            for collection, count in rows
        ]

    async def delete_collection(self, *, owner_id: uuid.UUID, collection_id: uuid.UUID) -> None:
        """Delete one of the owner's collections.

        Args:
            owner_id: The account the collection must belong to.
            collection_id: The collection to delete.

        Raises:
            NotFoundError: If no such collection belongs to the owner.
        """
        collection = await self._require_collection(owner_id=owner_id, collection_id=collection_id)
        await self._collections.delete(collection)
        _logger.info("collection_deleted", collection_id=str(collection_id))

    async def add_to_collection(
        self, *, owner_id: uuid.UUID, collection_id: uuid.UUID, vehicle_id: uuid.UUID
    ) -> None:
        """Add one of the owner's vehicles to one of their collections.

        Both the collection and the vehicle are checked against the owner, so a
        caller cannot file somebody else's vehicle into their own collection.

        Args:
            owner_id: The account both records must belong to.
            collection_id: The target collection.
            vehicle_id: The vehicle to add.

        Raises:
            NotFoundError: If either record does not belong to the owner.
            ConflictError: If the vehicle is already in the collection.
        """
        collection = await self._require_collection(owner_id=owner_id, collection_id=collection_id)
        vehicle = await self._require(owner_id=owner_id, vehicle_id=vehicle_id)

        if await self._collections.contains(collection_id=collection.id, vehicle_id=vehicle.id):
            raise ConflictError("This vehicle is already in the collection.")

        self._collections.add_item(
            CollectionItem(collection_id=collection.id, vehicle_id=vehicle.id)
        )
        await self._collections.flush()

    async def remove_from_collection(
        self, *, owner_id: uuid.UUID, collection_id: uuid.UUID, vehicle_id: uuid.UUID
    ) -> None:
        """Remove a vehicle from one of the owner's collections.

        Args:
            owner_id: The account the collection must belong to.
            collection_id: The target collection.
            vehicle_id: The vehicle to remove.

        Raises:
            NotFoundError: If the collection does not belong to the owner, or
                the vehicle was not in it.
        """
        collection = await self._require_collection(owner_id=owner_id, collection_id=collection_id)
        removed = await self._collections.remove_item(
            collection_id=collection.id, vehicle_id=vehicle_id
        )
        if not removed:
            raise NotFoundError.for_resource("Collection membership", vehicle_id)

    async def _require(self, *, owner_id: uuid.UUID, vehicle_id: uuid.UUID) -> Vehicle:
        """Fetch a vehicle or raise if it is not the owner's."""
        vehicle = await self._vehicles.get_for_owner(owner_id=owner_id, vehicle_id=vehicle_id)
        if vehicle is None:
            raise NotFoundError.for_resource("Vehicle", vehicle_id)
        return vehicle

    async def _require_collection(
        self, *, owner_id: uuid.UUID, collection_id: uuid.UUID
    ) -> Collection:
        """Fetch a collection or raise if it is not the owner's."""
        collection = await self._collections.get_for_owner(
            owner_id=owner_id, collection_id=collection_id
        )
        if collection is None:
            raise NotFoundError.for_resource("Collection", collection_id)
        return collection

    @staticmethod
    def _window_start(window_days: int) -> datetime:
        """The earliest instant included in a price comparison window."""
        return datetime.now(UTC) - timedelta(days=window_days)


def _build_trend(movement: PriceMovement | None, *, window_days: int) -> PriceTrend | None:
    """Summarise a price movement for the wire.

    Returns ``None`` when there is nothing observed in the window, which the
    client renders as "no price change recorded" rather than as a zero change.
    """
    if movement is None:
        return None

    # A single observation cannot describe a movement, so the change is left
    # unset rather than reported as zero, which would read as "price held".
    has_comparison = movement.observation_count > 1
    absolute = movement.newest - movement.oldest if has_comparison else None

    percentage: Decimal | None = None
    if absolute is not None and movement.oldest != 0:
        percentage = (absolute / movement.oldest * _PERCENT).quantize(
            _PERCENT_QUANTUM, rounding=ROUND_HALF_UP
        )

    return PriceTrend(
        current_price=movement.newest,
        previous_price=movement.oldest if has_comparison else None,
        absolute_change=absolute,
        percentage_change=percentage,
        window_days=window_days,
        observation_count=movement.observation_count,
    )


def _collapse_to_daily_points(snapshots: Sequence[PriceSnapshot]) -> list[PriceHistoryPoint]:
    """Reduce observations to one point per local day, keeping the last of each.

    The chart plots days, so several observations on one day must collapse to a
    single point; the last one is kept because it is what the price ended at.
    """
    by_day: dict[date, PriceHistoryPoint] = {}
    for snapshot in snapshots:
        local_day = snapshot.observed_at.astimezone(APP_TIMEZONE).date()
        by_day[local_day] = PriceHistoryPoint(observed_on=local_day, price=snapshot.price)
    return [by_day[day] for day in sorted(by_day)]
