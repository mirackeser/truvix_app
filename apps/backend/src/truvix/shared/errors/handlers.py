"""Translation of exceptions into RFC 9457 problem detail responses.

Every error the API returns has the same shape, so mobile and web clients can
implement a single error path. Unexpected exceptions are logged with a full
traceback but reported to the caller without internal details.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from truvix.shared.errors.exceptions import (
    AccountLockedError,
    RateLimitExceededError,
    TruvixError,
)
from truvix.shared.logging import get_logger

_logger = get_logger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"

# Base URI namespace for machine-readable problem types.
_PROBLEM_TYPE_BASE = "https://docs.truvix.app/errors"

_REQUEST_ID_HEADER = "X-Request-ID"


def _problem_response(
    *,
    request: Request,
    status_code: int,
    error_code: str,
    title: str,
    detail: str,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a problem detail response body and attach correlation headers."""
    request_id = getattr(request.state, "request_id", None)
    body: dict[str, Any] = {
        "type": f"{_PROBLEM_TYPE_BASE}/{error_code}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
        "code": error_code,
    }
    if extra:
        body["errors"] = extra
    if request_id:
        body["requestId"] = request_id

    response_headers = dict(headers or {})
    if request_id:
        response_headers[_REQUEST_ID_HEADER] = request_id

    return JSONResponse(
        status_code=status_code,
        content=body,
        headers=response_headers,
        media_type=PROBLEM_CONTENT_TYPE,
    )


async def handle_truvix_error(request: Request, exc: TruvixError) -> JSONResponse:
    """Render a deliberate domain error."""
    headers: dict[str, str] = {}
    if isinstance(exc, RateLimitExceededError | AccountLockedError):
        headers["Retry-After"] = str(exc.retry_after_seconds)

    _logger.warning(
        "domain_error",
        error_code=exc.error_code,
        status_code=exc.status_code,
        detail=exc.message,
        **exc.details,
    )
    return _problem_response(
        request=request,
        status_code=exc.status_code,
        error_code=exc.error_code,
        title=exc.title,
        detail=exc.message,
        extra=exc.details or None,
        headers=headers,
    )


async def handle_request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Render a schema validation failure as a field-level problem report."""
    field_errors = [
        {
            "field": ".".join(str(part) for part in error["loc"][1:]) or "body",
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    _logger.info("request_validation_failed", field_count=len(field_errors))
    return _problem_response(
        request=request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        error_code="validation_failed",
        title="Validation Failed",
        detail="The request body failed validation.",
        extra={"fields": field_errors},
    )


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Render framework-raised HTTP errors, such as 404 for unknown routes."""
    http_status = HTTPStatus(exc.status_code)
    return _problem_response(
        request=request,
        status_code=exc.status_code,
        error_code=http_status.phrase.lower().replace(" ", "_"),
        title=http_status.phrase,
        detail=str(exc.detail),
        headers=dict(exc.headers or {}),
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Render an unhandled exception without leaking internals to the caller."""
    _logger.exception(
        "unhandled_exception",
        exception_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
    )
    return _problem_response(
        request=request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code="internal_error",
        title="Internal Server Error",
        detail="An unexpected error occurred. The incident has been recorded.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach every exception handler to the application.

    Args:
        app: The FastAPI application to configure.
    """
    app.add_exception_handler(TruvixError, handle_truvix_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, handle_unexpected_error)
