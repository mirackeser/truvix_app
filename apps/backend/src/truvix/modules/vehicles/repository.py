"""Data access for garage vehicles, price history and collections.

Every method that reads or writes a vehicle takes the owner's id and filters on
it. That is deliberate and load-bearing: it makes it impossible to write a
handler that fetches by identifier alone and accidentally serves one user's
garage to another.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncSession

from truvix.modules.vehicles.models import (
    Collection,
    CollectionItem,
    PriceSnapshot,
    Vehicle,
)
from truvix.modules.vehicles.schemas import GarageFilter, VehicleSort
from truvix.shared.pagination import PageParams


@dataclass(frozen=True, slots=True)
class PriceMovement:
    """Newest and oldest observed prices for a vehicle inside a window."""

    newest: Decimal
    oldest: Decimal
    observation_count: int


@dataclass(frozen=True, slots=True)
class GarageCounts:
    """Vehicle counts backing the garage screen's tabs."""

    total: int
    favourites: int
    in_comparison: int
    viewed_today: int


class VehicleRepository:
    """Reads and writes garage vehicles."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the repository.

        Args:
            session: The session whose transaction this repository participates in.
        """
        self._session = session

    async def get_for_owner(self, *, owner_id: uuid.UUID, vehicle_id: uuid.UUID) -> Vehicle | None:
        """Fetch one of the owner's vehicles.

        Args:
            owner_id: The account the vehicle must belong to.
            vehicle_id: The vehicle to fetch.

        Returns:
            The vehicle, or ``None`` when it does not exist, was deleted, or
            belongs to somebody else. The three cases are deliberately
            indistinguishable so the API cannot confirm that another user's
            vehicle exists.
        """
        statement = select(Vehicle).where(
            Vehicle.id == vehicle_id,
            Vehicle.user_id == owner_id,
            Vehicle.deleted_at.is_(None),
        )
        vehicle: Vehicle | None = await self._session.scalar(statement)
        return vehicle

    async def list_for_owner(
        self,
        *,
        owner_id: uuid.UUID,
        garage_filter: GarageFilter,
        sort: VehicleSort,
        params: PageParams,
        price_window_start: datetime,
        day_start: datetime,
    ) -> tuple[Sequence[Vehicle], int]:
        """List a page of the owner's garage.

        Args:
            owner_id: The account whose garage to read.
            garage_filter: Which slice of the garage to return.
            sort: Ordering to apply.
            params: Pagination parameters.
            price_window_start: Earliest observation considered when deciding
                whether a price dropped.
            day_start: Start of the current local day, for "viewed today".

        Returns:
            The page's vehicles and the total number matching the filter.
        """
        base = self._owned(owner_id)
        base = self._apply_filter(
            base,
            garage_filter=garage_filter,
            price_window_start=price_window_start,
            day_start=day_start,
        )

        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))

        listing = self._apply_sort(base, sort).offset(params.offset).limit(params.limit)
        result = await self._session.scalars(listing)
        return result.all(), int(total or 0)

    async def counts_for_owner(self, *, owner_id: uuid.UUID, day_start: datetime) -> GarageCounts:
        """Count the owner's vehicles per tab in a single query.

        Args:
            owner_id: The account whose garage to count.
            day_start: Start of the current local day, for "viewed today".
        """
        statement = select(
            func.count().label("total"),
            func.count().filter(Vehicle.is_favourite).label("favourites"),
            func.count().filter(Vehicle.is_in_comparison).label("in_comparison"),
            func.count().filter(Vehicle.last_viewed_at >= day_start).label("viewed_today"),
        ).where(Vehicle.user_id == owner_id, Vehicle.deleted_at.is_(None))

        row = (await self._session.execute(statement)).one()
        return GarageCounts(
            total=row.total,
            favourites=row.favourites,
            in_comparison=row.in_comparison,
            viewed_today=row.viewed_today,
        )

    async def count_with_dropped_price(
        self, *, owner_id: uuid.UUID, price_window_start: datetime
    ) -> int:
        """Count the owner's vehicles whose price fell inside the window.

        Args:
            owner_id: The account whose garage to count.
            price_window_start: Earliest observation to consider.
        """
        statement = (
            select(func.count())
            .select_from(Vehicle)
            .where(
                Vehicle.user_id == owner_id,
                Vehicle.deleted_at.is_(None),
                Vehicle.id.in_(self._dropped_price_vehicle_ids(price_window_start)),
            )
        )
        return int(await self._session.scalar(statement) or 0)

    async def price_movements(
        self, *, vehicle_ids: Sequence[uuid.UUID], since: datetime
    ) -> dict[uuid.UUID, PriceMovement]:
        """Summarise price movement for several vehicles at once.

        Fetching the whole page's movements in one query keeps the garage list
        at two round trips regardless of page size, instead of one per card.

        Args:
            vehicle_ids: Vehicles to summarise.
            since: Earliest observation to consider.

        Returns:
            A mapping from vehicle id to its movement. Vehicles without any
            observation in the window are absent.
        """
        if not vehicle_ids:
            return {}

        newest = func.array_agg(
            aggregate_order_by(PriceSnapshot.price, PriceSnapshot.observed_at.desc())
        )[1]
        oldest = func.array_agg(
            aggregate_order_by(PriceSnapshot.price, PriceSnapshot.observed_at.asc())
        )[1]

        statement = (
            select(
                PriceSnapshot.vehicle_id,
                newest.label("newest"),
                oldest.label("oldest"),
                func.count().label("observations"),
            )
            .where(
                PriceSnapshot.vehicle_id.in_(vehicle_ids),
                PriceSnapshot.observed_at >= since,
            )
            .group_by(PriceSnapshot.vehicle_id)
        )

        rows = (await self._session.execute(statement)).all()
        return {
            row.vehicle_id: PriceMovement(
                newest=row.newest,
                oldest=row.oldest,
                observation_count=row.observations,
            )
            for row in rows
        }

    async def price_history(
        self, *, vehicle_id: uuid.UUID, since: datetime
    ) -> Sequence[PriceSnapshot]:
        """Read one vehicle's observations inside a window, oldest first.

        Args:
            vehicle_id: The vehicle whose history to read.
            since: Earliest observation to include.
        """
        statement = (
            select(PriceSnapshot)
            .where(PriceSnapshot.vehicle_id == vehicle_id, PriceSnapshot.observed_at >= since)
            .order_by(PriceSnapshot.observed_at.asc())
        )
        result = await self._session.scalars(statement)
        return result.all()

    def add(self, vehicle: Vehicle) -> None:
        """Stage a new vehicle for insertion."""
        self._session.add(vehicle)

    def add_price_snapshot(self, snapshot: PriceSnapshot) -> None:
        """Stage a new price observation for insertion."""
        self._session.add(snapshot)

    async def flush(self) -> None:
        """Send pending changes to the database without committing."""
        await self._session.flush()

    @staticmethod
    def _owned(owner_id: uuid.UUID) -> Select[tuple[Vehicle]]:
        """Start a query restricted to one owner's live vehicles."""
        return select(Vehicle).where(
            Vehicle.user_id == owner_id,
            Vehicle.deleted_at.is_(None),
        )

    @staticmethod
    def _dropped_price_vehicle_ids(since: datetime) -> Select[tuple[uuid.UUID]]:
        """Select vehicles whose newest price is below their oldest in a window."""
        newest = func.array_agg(
            aggregate_order_by(PriceSnapshot.price, PriceSnapshot.observed_at.desc())
        )[1]
        oldest = func.array_agg(
            aggregate_order_by(PriceSnapshot.price, PriceSnapshot.observed_at.asc())
        )[1]
        return (
            select(PriceSnapshot.vehicle_id)
            .where(PriceSnapshot.observed_at >= since)
            .group_by(PriceSnapshot.vehicle_id)
            .having(newest < oldest)
        )

    def _apply_filter(
        self,
        statement: Select[tuple[Vehicle]],
        *,
        garage_filter: GarageFilter,
        price_window_start: datetime,
        day_start: datetime,
    ) -> Select[tuple[Vehicle]]:
        """Narrow a garage query to the requested tab."""
        match garage_filter:
            case GarageFilter.ALL:
                return statement
            case GarageFilter.FAVOURITES:
                return statement.where(Vehicle.is_favourite)
            case GarageFilter.COMPARISON:
                return statement.where(Vehicle.is_in_comparison)
            case GarageFilter.VIEWED_TODAY:
                return statement.where(Vehicle.last_viewed_at >= day_start)
            case GarageFilter.PRICE_DROPPED:
                return statement.where(
                    Vehicle.id.in_(self._dropped_price_vehicle_ids(price_window_start))
                )

    @staticmethod
    def _apply_sort(statement: Select[tuple[Vehicle]], sort: VehicleSort) -> Select[tuple[Vehicle]]:
        """Order a garage query, always with a tie-break for stable paging."""
        match sort:
            case VehicleSort.RECENTLY_ADDED:
                return statement.order_by(Vehicle.created_at.desc(), Vehicle.id.desc())
            case VehicleSort.RECENTLY_VIEWED:
                return statement.order_by(
                    Vehicle.last_viewed_at.desc().nulls_last(), Vehicle.id.desc()
                )
            case VehicleSort.PRICE_ASCENDING:
                return statement.order_by(Vehicle.asking_price.asc(), Vehicle.id.desc())
            case VehicleSort.PRICE_DESCENDING:
                return statement.order_by(Vehicle.asking_price.desc(), Vehicle.id.desc())


class CollectionRepository:
    """Reads and writes user-created collections."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the repository.

        Args:
            session: The session whose transaction this repository participates in.
        """
        self._session = session

    async def get_for_owner(
        self, *, owner_id: uuid.UUID, collection_id: uuid.UUID
    ) -> Collection | None:
        """Fetch one of the owner's collections."""
        statement = select(Collection).where(
            Collection.id == collection_id,
            Collection.user_id == owner_id,
        )
        collection: Collection | None = await self._session.scalar(statement)
        return collection

    async def list_for_owner(self, *, owner_id: uuid.UUID) -> Sequence[tuple[Collection, int]]:
        """List the owner's collections with the size of each.

        Returns:
            Pairs of collection and vehicle count, newest collection first.
        """
        statement = (
            select(Collection, func.count(CollectionItem.vehicle_id))
            .outerjoin(CollectionItem, CollectionItem.collection_id == Collection.id)
            .where(Collection.user_id == owner_id)
            .group_by(Collection.id)
            .order_by(Collection.created_at.desc())
        )
        rows = (await self._session.execute(statement)).all()
        return [(row[0], row[1]) for row in rows]

    async def name_is_taken(self, *, owner_id: uuid.UUID, name: str) -> bool:
        """Whether the owner already has a collection with this name."""
        statement = (
            select(Collection.id)
            .where(Collection.user_id == owner_id, Collection.name == name)
            .limit(1)
        )
        return await self._session.scalar(statement) is not None

    async def contains(self, *, collection_id: uuid.UUID, vehicle_id: uuid.UUID) -> bool:
        """Whether a vehicle is already in a collection."""
        statement = (
            select(CollectionItem.vehicle_id)
            .where(
                CollectionItem.collection_id == collection_id,
                CollectionItem.vehicle_id == vehicle_id,
            )
            .limit(1)
        )
        return await self._session.scalar(statement) is not None

    def add(self, collection: Collection) -> None:
        """Stage a new collection for insertion."""
        self._session.add(collection)

    def add_item(self, item: CollectionItem) -> None:
        """Stage a new collection membership for insertion."""
        self._session.add(item)

    async def remove_item(self, *, collection_id: uuid.UUID, vehicle_id: uuid.UUID) -> bool:
        """Remove a vehicle from a collection.

        Returns:
            ``True`` when a membership was removed, ``False`` when there was
            nothing to remove.
        """
        item = await self._session.get(CollectionItem, (collection_id, vehicle_id))
        if item is None:
            return False
        await self._session.delete(item)
        await self._session.flush()
        return True

    async def delete(self, collection: Collection) -> None:
        """Delete a collection and its memberships."""
        await self._session.delete(collection)
        await self._session.flush()

    async def flush(self) -> None:
        """Send pending changes to the database without committing."""
        await self._session.flush()
