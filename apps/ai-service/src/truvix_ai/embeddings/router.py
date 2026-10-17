"""
API routes for the Embeddings module.

Exposes endpoints for generating vehicle embeddings and performing similarity searches.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException

from truvix_ai.embeddings.schemas import (
    VehicleEmbeddingRequest,
    SimilarVehicleRequest,
    SimilarVehicleResponse
)
from truvix_ai.embeddings.service import EmbeddingService
from truvix_ai.core.errors import ServiceUnavailableError

router = APIRouter(prefix='/api/v1/embeddings', tags=['Embeddings'])


def get_service(request: Request) -> EmbeddingService:
    app = request.app
    chat_model = getattr(app.state, 'chat_model', None)
    vector_store = getattr(app.state, 'vector_store', None)
    
    service = EmbeddingService(chat_model=chat_model, store=vector_store)
    if not service.is_available:
        raise ServiceUnavailableError("Embedding service is not available.")
    return service


@router.post('/vehicle', response_model=dict[str, str])
async def store_vehicle_embedding(request: Request, body: VehicleEmbeddingRequest) -> dict[str, str]:
    """Upserts a vehicle embedding into the vector store."""
    service = get_service(request)
    await service.upsert_vehicle(body)
    return {"vehicle_id": body.vehicle_id, "status": "stored"}


@router.post('/search', response_model=SimilarVehicleResponse)
async def search_similar_vehicles(request: Request, body: SimilarVehicleRequest) -> SimilarVehicleResponse:
    """Finds vehicles similar to the provided query vehicle."""
    service = get_service(request)
    return await service.find_similar(body)
