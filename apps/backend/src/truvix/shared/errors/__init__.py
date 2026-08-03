"""Domain errors and their HTTP representation."""

from truvix.shared.errors.exceptions import (
    AccountLockedError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DomainValidationError,
    ExternalServiceError,
    NotFoundError,
    RateLimitExceededError,
    ServiceUnavailableError,
    TruvixError,
)
from truvix.shared.errors.handlers import PROBLEM_CONTENT_TYPE, register_exception_handlers

__all__ = [
    "PROBLEM_CONTENT_TYPE",
    "AccountLockedError",
    "AuthenticationError",
    "AuthorizationError",
    "ConflictError",
    "DomainValidationError",
    "ExternalServiceError",
    "NotFoundError",
    "RateLimitExceededError",
    "ServiceUnavailableError",
    "TruvixError",
    "register_exception_handlers",
]
