"""Custom exception types for the AI service."""
from __future__ import annotations

from typing import Any


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


class QuotaExceededError(Exception):
    """Raised when usage limits are exceeded."""
    pass


class ServiceUnavailableError(Exception):
    """Raised when the service is temporarily down."""
    pass


class ExternalServiceError(Exception):
    """Raised when a downstream external dependency (e.g. LLM API) fails."""

    def __init__(self, service: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.service = service
        self.message = message
        self.details = details or {}
        super().__init__(f"External service '{service}' error: {message}")
