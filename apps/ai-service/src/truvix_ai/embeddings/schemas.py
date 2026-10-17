"""
Defines schemas for the Embeddings module.

These schemas represent the data structures used for vector representations
of vehicles and similarity search functionality.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class VehicleEmbeddingRequest(BaseModel):
    vehicle_id: str
    make: str
    model: str
    model_year: int
    mileage_km: int
    fuel_type: str | None = None
    transmission: str | None = None
    body_type: str | None = None
    price: Decimal | None = None
    currency: str = 'TRY'
    trust_score: int | None = None


class SimilarVehicleRequest(BaseModel):
    query_vehicle: VehicleEmbeddingRequest
    top_k: int = Field(default=5, ge=1, le=20)


class SimilarVehicleResult(BaseModel):
    vehicle_id: str
    similarity_score: float
    metadata: dict[str, Any]


class SimilarVehicleResponse(BaseModel):
    results: list[SimilarVehicleResult]
    query_vehicle_id: str
