"""
Service layer for the Embeddings module.

Handles generation of vector embeddings for vehicles and interaction
with the vector database for similarity search.
"""
from __future__ import annotations

import httpx
from typing import Any

from truvix_ai.core.chat import ChatModel
from truvix_ai.embeddings.schemas import (
    VehicleEmbeddingRequest,
    SimilarVehicleRequest,
    SimilarVehicleResponse,
    SimilarVehicleResult
)
from truvix_ai.config import get_settings
from truvix_ai.observability.logging import get_logger
from truvix_ai.embeddings.store import VectorStore

logger = get_logger(__name__)


class EmbeddingService:
    def __init__(self, chat_model: ChatModel | None, store: VectorStore | None):
        self.chat_model = chat_model
        self.store = store
        self.settings = get_settings()

    async def embed_vehicle(self, request: VehicleEmbeddingRequest) -> list[float]:
        """
        Generates an embedding vector for a vehicle.
        """
        text_rep = (
            f"Marka: {request.make}, Model: {request.model}, Yıl: {request.model_year}, "
            f"Kilometre: {request.mileage_km} km, Yakıt: {request.fuel_type or 'Bilinmiyor'}, "
            f"Vites: {request.transmission or 'Bilinmiyor'}, "
            f"Fiyat: {request.price if request.price is not None else 'Bilinmiyor'} {request.currency}"
        )
        
        api_key = getattr(self.settings, 'openai_api_key', '')
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "input": text_rep,
                        "model": "text-embedding-3-small"
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                return data["data"][0]["embedding"]
        except Exception as e:
            logger.error("embeddings.embed_vehicle_failed", error=str(e))
            # Graceful degradation: return zero vector
            return [0.0] * 1536

    async def upsert_vehicle(self, request: VehicleEmbeddingRequest) -> None:
        """
        Generates an embedding and stores it in the vector database.
        """
        if not self.store:
            logger.warning("embeddings.store_not_configured")
            return
            
        embedding = await self.embed_vehicle(request)
        
        metadata = request.model_dump(exclude={'vehicle_id', 'price'})
        if request.price is not None:
            metadata['price'] = float(request.price)
            
        document = f"{request.make} {request.model} {request.model_year}"
            
        self.store.upsert(
            id=request.vehicle_id,
            embedding=embedding,
            metadata=metadata,
            document=document
        )

    async def find_similar(self, request: SimilarVehicleRequest) -> SimilarVehicleResponse:
        """
        Finds vehicles similar to the query vehicle.
        """
        if not self.store:
            logger.warning("embeddings.store_not_configured")
            return SimilarVehicleResponse(results=[], query_vehicle_id=request.query_vehicle.vehicle_id)
            
        query_embedding = await self.embed_vehicle(request.query_vehicle)
        
        results_data = self.store.query(
            embedding=query_embedding,
            top_k=request.top_k
        )
        
        results = []
        for res_id, score, metadata in results_data:
            if res_id != request.query_vehicle.vehicle_id:
                results.append(
                    SimilarVehicleResult(
                        vehicle_id=res_id,
                        similarity_score=score,
                        metadata=metadata
                    )
                )
                
        return SimilarVehicleResponse(
            results=results,
            query_vehicle_id=request.query_vehicle.vehicle_id
        )

    @property
    def is_available(self) -> bool:
        """Checks if the embedding service is ready to handle requests."""
        return self.chat_model is not None and self.store is not None
