"""FastAPI application factory.

The factory takes settings as an argument rather than reading them from the
environment itself, so the test suite can build an application against a
throwaway database without mutating process-wide state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from truvix import __version__
from truvix.api.health import router as health_router
from truvix.api.router import build_api_v1_router
from truvix.modules.notifications.handlers import register_notification_handlers
from truvix.shared.config import Settings, get_settings
from truvix.shared.container import ApplicationContainer
from truvix.shared.errors import register_exception_handlers
from truvix.shared.logging import configure_logging, get_logger
from truvix.shared.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from truvix.shared.transaction import TransactionMiddleware

_logger = get_logger(__name__)

_API_DESCRIPTION = """
Truvix is an AI-assisted vehicle intelligence platform. The API powers vehicle
analysis, price tracking and the AI copilot used by the Truvix mobile client.

Errors are returned as RFC 9457 problem details with a stable `code` field.
"""


type LifespanFactory = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def _build_lifespan(settings: Settings) -> LifespanFactory:
    """Create the lifespan handler bound to the given settings."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Open shared resources on startup and release them on shutdown."""
        container = ApplicationContainer(settings)
        app.state.container = container
        _logger.info(
            "application_started",
            environment=settings.environment.value,
            version=__version__,
        )
        try:
            yield
        finally:
            await container.aclose()
            _logger.info("application_stopped")

    return lifespan


def _register_middleware(app: FastAPI, settings: Settings) -> None:
    """Attach middleware in the order responses should pass through it."""
    # Starlette applies middleware bottom-up, so the last registered runs first.
    # Outermost of the application middlewares, so the transaction encloses
    # everything that could write — including the exception handlers that turn
    # a failure into a response.
    app.add_middleware(TransactionMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware, settings=settings.observability)

    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
            max_age=600,
        )

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)


def _register_routes(app: FastAPI, settings: Settings) -> None:
    """Mount every router onto the application.

    Probes are mounted at the root so orchestrators can reach them without
    knowing the API version; feature routers live under the versioned prefix.
    """
    app.include_router(health_router)
    app.include_router(build_api_v1_router(), prefix=settings.api_v1_prefix)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fully configured FastAPI application.

    Args:
        settings: Configuration to build against. Defaults to the process-wide
            settings loaded from the environment.

    Returns:
        An application ready to be served by an ASGI server.
    """
    resolved = settings or get_settings()
    configure_logging(resolved.observability)

    app = FastAPI(
        title=resolved.app_name,
        version=__version__,
        description=_API_DESCRIPTION,
        docs_url=resolved.docs_url,
        redoc_url=None,
        openapi_url=resolved.openapi_url,
        lifespan=_build_lifespan(resolved),
    )

    _register_middleware(app, resolved)
    register_exception_handlers(app)
    _register_routes(app, resolved)
    register_notification_handlers()

    return app


app = create_app()
