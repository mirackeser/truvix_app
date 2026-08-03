"""Dependency providers for the garage endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from truvix.modules.vehicles.repository import CollectionRepository, VehicleRepository
from truvix.modules.vehicles.service import VehicleService
from truvix.shared.dependencies import SessionDep


def get_vehicle_repository(session: SessionDep) -> VehicleRepository:
    """Provide the vehicle repository bound to the request's transaction."""
    return VehicleRepository(session)


def get_collection_repository(session: SessionDep) -> CollectionRepository:
    """Provide the collection repository bound to the request's transaction."""
    return CollectionRepository(session)


VehicleRepositoryDep = Annotated[VehicleRepository, Depends(get_vehicle_repository)]
CollectionRepositoryDep = Annotated[CollectionRepository, Depends(get_collection_repository)]


def get_vehicle_service(
    vehicles: VehicleRepositoryDep,
    collections: CollectionRepositoryDep,
) -> VehicleService:
    """Provide the garage service for the current request."""
    return VehicleService(vehicles=vehicles, collections=collections)


VehicleServiceDep = Annotated[VehicleService, Depends(get_vehicle_service)]
