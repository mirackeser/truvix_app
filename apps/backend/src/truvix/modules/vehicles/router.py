"""HTTP endpoints for the garage: vehicles, price tracking and collections."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from truvix.modules.auth.dependencies import CurrentUserDep
from truvix.modules.vehicles.dependencies import VehicleServiceDep
from truvix.modules.vehicles.schemas import (
    CollectionCreateRequest,
    CollectionResponse,
    GarageFilter,
    GarageStatsResponse,
    PriceHistoryResponse,
    PriceSnapshotResponse,
    PriceUpdateRequest,
    VehicleCreateRequest,
    VehicleResponse,
    VehicleSort,
    VehicleSummaryResponse,
    VehicleUpdateRequest,
)
from truvix.modules.vehicles.service import (
    DEFAULT_PRICE_WINDOW_DAYS,
    MAX_PRICE_WINDOW_DAYS,
)
from truvix.shared.errors import PROBLEM_CONTENT_TYPE
from truvix.shared.pagination import Page, PageParamsDep

router = APIRouter(prefix="/vehicles", tags=["vehicles"])
collections_router = APIRouter(prefix="/collections", tags=["collections"])

_PROBLEM: dict[str, Any] = {"content": {PROBLEM_CONTENT_TYPE: {}}}
_UNAUTHORISED: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"description": "Access token missing or invalid.", **_PROBLEM},
}
_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    **_UNAUTHORISED,
    status.HTTP_404_NOT_FOUND: {
        "description": "No such vehicle in this account's garage.",
        **_PROBLEM,
    },
}

WindowDays = Annotated[
    int,
    Query(
        ge=1,
        le=MAX_PRICE_WINDOW_DAYS,
        description="How many days of price history to consider.",
    ),
]


@router.post(
    "",
    response_model=VehicleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a vehicle",
    description=(
        "Adds a vehicle to the caller's garage and records its asking price as "
        "the first observation in its price history."
    ),
    responses=_UNAUTHORISED,
)
async def create_vehicle(
    payload: VehicleCreateRequest,
    current_user: CurrentUserDep,
    service: VehicleServiceDep,
) -> VehicleResponse:
    """Save a vehicle to the caller's garage."""
    vehicle = await service.create(owner_id=current_user.id, payload=payload)
    return VehicleResponse.from_vehicle(vehicle)


@router.get(
    "",
    response_model=Page[VehicleSummaryResponse],
    summary="List the garage",
    description="Returns a page of the caller's saved vehicles with price movement.",
    responses=_UNAUTHORISED,
)
async def list_vehicles(
    current_user: CurrentUserDep,
    service: VehicleServiceDep,
    params: PageParamsDep,
    garage_filter: Annotated[
        GarageFilter, Query(alias="filter", description="Which garage tab to return.")
    ] = GarageFilter.ALL,
    sort: VehicleSort = VehicleSort.RECENTLY_ADDED,
    window_days: WindowDays = DEFAULT_PRICE_WINDOW_DAYS,
) -> Page[VehicleSummaryResponse]:
    """List the caller's garage."""
    return await service.list_garage(
        owner_id=current_user.id,
        garage_filter=garage_filter,
        sort=sort,
        params=params,
        window_days=window_days,
    )


@router.get(
    "/stats",
    response_model=GarageStatsResponse,
    summary="Garage counts",
    description="Returns the vehicle count behind each garage tab.",
    responses=_UNAUTHORISED,
)
async def read_garage_stats(
    current_user: CurrentUserDep,
    service: VehicleServiceDep,
    window_days: WindowDays = DEFAULT_PRICE_WINDOW_DAYS,
) -> GarageStatsResponse:
    """Return the counts backing the garage tabs."""
    return await service.garage_stats(owner_id=current_user.id, window_days=window_days)


@router.get(
    "/{vehicle_id}",
    response_model=VehicleResponse,
    summary="Read a vehicle",
    description="Returns one saved vehicle and marks it as viewed.",
    responses=_NOT_FOUND,
)
async def read_vehicle(
    vehicle_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: VehicleServiceDep,
) -> VehicleResponse:
    """Return one of the caller's vehicles."""
    vehicle = await service.get(owner_id=current_user.id, vehicle_id=vehicle_id)
    return VehicleResponse.from_vehicle(vehicle)


@router.patch(
    "/{vehicle_id}",
    response_model=VehicleResponse,
    summary="Update a vehicle",
    description=(
        "Applies a partial update. Changing the asking price also records a new price observation."
    ),
    responses=_NOT_FOUND,
)
async def update_vehicle(
    vehicle_id: uuid.UUID,
    payload: VehicleUpdateRequest,
    current_user: CurrentUserDep,
    service: VehicleServiceDep,
) -> VehicleResponse:
    """Update one of the caller's vehicles."""
    vehicle = await service.update(owner_id=current_user.id, vehicle_id=vehicle_id, payload=payload)
    return VehicleResponse.from_vehicle(vehicle)


@router.delete(
    "/{vehicle_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a vehicle",
    description="Removes a vehicle from the garage, retaining its history for recovery.",
    responses=_NOT_FOUND,
)
async def delete_vehicle(
    vehicle_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: VehicleServiceDep,
) -> None:
    """Remove one of the caller's vehicles."""
    await service.delete(owner_id=current_user.id, vehicle_id=vehicle_id)


@router.post(
    "/{vehicle_id}/prices",
    response_model=PriceSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a price",
    description="Records a newly observed asking price for a saved vehicle.",
    responses=_NOT_FOUND,
)
async def record_price(
    vehicle_id: uuid.UUID,
    payload: PriceUpdateRequest,
    current_user: CurrentUserDep,
    service: VehicleServiceDep,
) -> PriceSnapshotResponse:
    """Record a new price observation."""
    snapshot = await service.record_price(
        owner_id=current_user.id,
        vehicle_id=vehicle_id,
        price=payload.price,
        observed_at=payload.observed_at,
    )
    return PriceSnapshotResponse.from_snapshot(snapshot)


@router.get(
    "/{vehicle_id}/prices",
    response_model=PriceHistoryResponse,
    summary="Price history",
    description="Returns the price chart series and its summary trend.",
    responses=_NOT_FOUND,
)
async def read_price_history(
    vehicle_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: VehicleServiceDep,
    window_days: WindowDays = DEFAULT_PRICE_WINDOW_DAYS,
) -> PriceHistoryResponse:
    """Return a vehicle's price history."""
    return await service.price_history(
        owner_id=current_user.id, vehicle_id=vehicle_id, window_days=window_days
    )


@collections_router.post(
    "",
    response_model=CollectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a collection",
    description="Creates a named collection for grouping vehicles.",
    responses={
        **_UNAUTHORISED,
        status.HTTP_409_CONFLICT: {
            "description": "Name already used, or the account is at its collection limit.",
            **_PROBLEM,
        },
    },
)
async def create_collection(
    payload: CollectionCreateRequest,
    current_user: CurrentUserDep,
    service: VehicleServiceDep,
) -> CollectionResponse:
    """Create a collection."""
    collection = await service.create_collection(owner_id=current_user.id, name=payload.name)
    return CollectionResponse(
        id=collection.id,
        name=collection.name,
        vehicle_count=0,
        created_at=collection.created_at,
    )


@collections_router.get(
    "",
    response_model=list[CollectionResponse],
    summary="List collections",
    description="Returns the caller's collections and how many vehicles each holds.",
    responses=_UNAUTHORISED,
)
async def list_collections(
    current_user: CurrentUserDep,
    service: VehicleServiceDep,
) -> list[CollectionResponse]:
    """List the caller's collections."""
    return await service.list_collections(owner_id=current_user.id)


@collections_router.delete(
    "/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a collection",
    description="Deletes a collection. The vehicles in it are not affected.",
    responses=_NOT_FOUND,
)
async def delete_collection(
    collection_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: VehicleServiceDep,
) -> None:
    """Delete one of the caller's collections."""
    await service.delete_collection(owner_id=current_user.id, collection_id=collection_id)


@collections_router.put(
    "/{collection_id}/vehicles/{vehicle_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Add a vehicle to a collection",
    description="Files one of the caller's vehicles into one of their collections.",
    responses={
        **_NOT_FOUND,
        status.HTTP_409_CONFLICT: {
            "description": "The vehicle is already in this collection.",
            **_PROBLEM,
        },
    },
)
async def add_vehicle_to_collection(
    collection_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: VehicleServiceDep,
) -> None:
    """Add a vehicle to a collection."""
    await service.add_to_collection(
        owner_id=current_user.id, collection_id=collection_id, vehicle_id=vehicle_id
    )


@collections_router.delete(
    "/{collection_id}/vehicles/{vehicle_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a vehicle from a collection",
    description="Removes a vehicle from a collection without deleting the vehicle.",
    responses=_NOT_FOUND,
)
async def remove_vehicle_from_collection(
    collection_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: VehicleServiceDep,
) -> None:
    """Remove a vehicle from a collection."""
    await service.remove_from_collection(
        owner_id=current_user.id, collection_id=collection_id, vehicle_id=vehicle_id
    )
