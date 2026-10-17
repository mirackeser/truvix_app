"""FastAPI application factory and lifecycle management."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from truvix_ai import __version__
from truvix_ai.config import get_settings
from truvix_ai.core.openai_client import OpenAIChatModel
from truvix_ai.core.errors import ExternalServiceError

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle and resources."""
    settings = get_settings()
    
    # Initialize HTTP client for provider
    http_client = httpx.AsyncClient(timeout=settings.provider.request_timeout_seconds)
    
    # Initialize chat model if API key is present
    if settings.provider.enabled and settings.provider.api_key:
        chat_model = OpenAIChatModel(
            client=http_client,
            api_key=settings.provider.api_key,
            base_url=str(settings.provider.base_url),
            model=settings.provider.model,
            temperature=settings.provider.temperature,
            max_tokens=settings.provider.max_output_tokens,
        )
        app.state.chat_model = chat_model
        logger.info("AI provider configured successfully")
    else:
        app.state.chat_model = None
        logger.warning("AI provider is not configured. Features requiring AI will be disabled.")
    
    yield
    
    # Cleanup
    await http_client.aclose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Truvix AI Service",
        version=__version__,
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global Exception Handlers
    @app.exception_handler(ExternalServiceError)
    async def external_service_error_handler(
        request: Request, exc: ExternalServiceError
    ) -> JSONResponse:
        """Handle downstream service failures gracefully."""
        logger.error("external_service_error", service=exc.service, error=exc.message, details=exc.details)
        return JSONResponse(
            status_code=502,
            content={
                "error": "ai_service_unavailable",
                "message": "AI hizmeti şu anda kullanılamıyor. Lütfen daha sonra tekrar deneyin.",
            },
        )

    # Routers placeholder - you would include actual routers here
    @app.get("/healthz", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Simple health check endpoint."""
        return {"status": "ok", "version": __version__}

    return app
