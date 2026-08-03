"""HTTP middleware providing request correlation, access logging and security headers."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from truvix.shared.config import ObservabilitySettings, Settings
from truvix.shared.logging import bind_request_context, clear_request_context, get_logger

_logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
_MILLISECONDS_PER_SECOND = 1000

# Lowest HTTP status treated as a server-side failure when choosing log severity.
_SERVER_ERROR_STATUS_FLOOR = 500

# Paths excluded from access logging to keep probe traffic out of the log volume.
_UNLOGGED_PATHS = frozenset({"/health/live", "/health/ready", "/metrics"})

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}

_HSTS_HEADER = "Strict-Transport-Security"
_HSTS_VALUE = "max-age=31536000; includeSubDomains"

type _NextCall = Callable[[Request], Awaitable[Response]]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns each request a correlation id and logs its outcome.

    The id is taken from the inbound ``X-Request-ID`` header when a trusted
    proxy supplies one, and generated otherwise. It is bound into the logging
    context, echoed back on the response, and embedded in error bodies, so a
    user-reported failure can be traced to exact log lines.
    """

    def __init__(self, app: ASGIApp, settings: ObservabilitySettings) -> None:
        """Initialise the middleware.

        Args:
            app: The downstream ASGI application.
            settings: Observability configuration controlling slow-request logs.
        """
        super().__init__(app)
        self._slow_request_threshold_ms = settings.slow_request_threshold_ms

    async def dispatch(self, request: Request, call_next: _NextCall) -> Response:
        """Bind request context, time the call and emit an access log record."""
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid7())
        request.state.request_id = request_id

        bind_request_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started_at) * _MILLISECONDS_PER_SECOND
            _logger.exception("request_failed", duration_ms=round(duration_ms, 2))
            clear_request_context()
            raise

        duration_ms = (time.perf_counter() - started_at) * _MILLISECONDS_PER_SECOND
        response.headers[REQUEST_ID_HEADER] = request_id

        if request.url.path not in _UNLOGGED_PATHS:
            self._log_request(response.status_code, duration_ms)

        clear_request_context()
        return response

    def _log_request(self, status_code: int, duration_ms: float) -> None:
        """Emit the access log record at a severity matching the outcome."""
        rounded_ms = round(duration_ms, 2)
        if status_code >= _SERVER_ERROR_STATUS_FLOOR:
            _logger.error("request_completed", status_code=status_code, duration_ms=rounded_ms)
        elif duration_ms >= self._slow_request_threshold_ms:
            _logger.warning("request_slow", status_code=status_code, duration_ms=rounded_ms)
        else:
            _logger.info("request_completed", status_code=status_code, duration_ms=rounded_ms)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Applies hardening headers to every response.

    HSTS is only sent in production-like environments, because sending it from a
    local HTTP server would pin the developer's browser to HTTPS on localhost.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        """Initialise the middleware.

        Args:
            app: The downstream ASGI application.
            settings: Root settings used to decide whether HSTS applies.
        """
        super().__init__(app)
        self._send_hsts = settings.environment.is_production_like

    async def dispatch(self, request: Request, call_next: _NextCall) -> Response:
        """Attach security headers to the downstream response."""
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if self._send_hsts:
            response.headers.setdefault(_HSTS_HEADER, _HSTS_VALUE)
        return response
