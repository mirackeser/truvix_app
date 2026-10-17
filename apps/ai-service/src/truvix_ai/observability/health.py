"""
Health check endpoints.

Exposes liveness, readiness, and metrics endpoints for Kubernetes
or other orchestrators.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response

from truvix_ai.observability.metrics import metrics_endpoint

router = APIRouter(tags=['Observability'])


@router.get('/healthz')
async def liveness() -> dict[str, str]:
    """Liveness probe. Indicates if the application is running."""
    return {"status": "ok"}


@router.get('/readyz')
async def readiness(request: Request) -> dict[str, Any]:
    """Readiness probe. Indicates if the application is ready to receive traffic."""
    app = request.app
    
    chat_model = getattr(app.state, 'chat_model', None)
    vector_store = getattr(app.state, 'vector_store', None)
    
    ai_provider_ready = chat_model is not None
    vector_store_ready = vector_store is not None
    
    return {
        "status": "ready" if ai_provider_ready else "not_ready",
        "checks": {
            "ai_provider": ai_provider_ready,
            "vector_store": vector_store_ready
        }
    }


@router.get('/metrics')
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    return metrics_endpoint()
