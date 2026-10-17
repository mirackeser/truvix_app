"""
Vector Store wrapper.

Provides an abstraction over ChromaDB for storing and querying vector embeddings.
Gracefully handles missing dependencies or unavailable database.
"""
from __future__ import annotations

from typing import Any
from truvix_ai.observability.logging import get_logger

logger = get_logger(__name__)

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False


class VectorStore:
    def __init__(self, host: str, port: int, collection_name: str):
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        
        if HAS_CHROMA:
            try:
                self.client = chromadb.HttpClient(
                    host=host,
                    port=port,
                    settings=Settings(anonymized_telemetry=False)
                )
                self.collection = self.get_or_create_collection()
            except Exception as e:
                logger.warning("vector_store.connection_failed", error=str(e))
        else:
            logger.warning("vector_store.chromadb_not_installed")

    def get_or_create_collection(self) -> Any:
        if self.client:
            return self.client.get_or_create_collection(name=self.collection_name)
        return None

    def upsert(self, id: str, embedding: list[float], metadata: dict[str, Any], document: str) -> None:
        if not self.collection:
            logger.warning("vector_store.upsert_skipped_no_collection")
            return
            
        try:
            self.collection.upsert(
                ids=[id],
                embeddings=[embedding],
                metadatas=[metadata],
                documents=[document]
            )
        except Exception as e:
            logger.error("vector_store.upsert_failed", error=str(e))

    def query(self, embedding: list[float], top_k: int) -> list[tuple[str, float, dict[str, Any]]]:
        if not self.collection:
            logger.warning("vector_store.query_skipped_no_collection")
            return []
            
        try:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=top_k
            )
            
            parsed_results = []
            if results['ids'] and len(results['ids']) > 0:
                ids = results['ids'][0]
                distances = results['distances'][0] if 'distances' in results and results['distances'] else [0.0] * len(ids)
                metadatas = results['metadatas'][0] if 'metadatas' in results and results['metadatas'] else [{}] * len(ids)
                
                for i in range(len(ids)):
                    score = 1.0 - distances[i] if distances[i] is not None else 0.0
                    parsed_results.append((ids[i], score, metadatas[i]))
                    
            return parsed_results
        except Exception as e:
            logger.error("vector_store.query_failed", error=str(e))
            return []

    def delete(self, id: str) -> None:
        if not self.collection:
            return
            
        try:
            self.collection.delete(ids=[id])
        except Exception as e:
            logger.error("vector_store.delete_failed", error=str(e))
