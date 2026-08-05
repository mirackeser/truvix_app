"""Domain error hierarchy shared by every Truvix module.

Business code raises these exceptions without knowing anything about HTTP. The
transport layer translates them into RFC 9457 problem responses, which keeps the
service layer reusable from background workers and CLI entry points.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any


class TruvixError(Exception):
    """Base class for every error the application raises deliberately.

    Attributes:
        status_code: HTTP status the transport layer maps this error to.
        error_code: Stable, machine-readable identifier that clients may branch
            on. Unlike the human-readable message, it never changes wording.
        title: Short human-readable summary of the error category.
    """

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"
    title: str = "Internal Server Error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        """Initialise the error.

        Args:
            message: Human-readable explanation safe to return to the caller.
            details: Structured, non-sensitive context describing the failure.
        """
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.error_code!r}, message={self.message!r})"


class NotFoundError(TruvixError):
    """A requested resource does not exist or is not visible to the caller."""

    status_code = HTTPStatus.NOT_FOUND
    error_code = "not_found"
    title = "Resource Not Found"

    @classmethod
    def for_resource(cls, resource: str, identifier: object) -> NotFoundError:
        """Build a consistently worded error for a missing resource."""
        return cls(
            f"{resource} was not found.",
            details={"resource": resource, "identifier": str(identifier)},
        )


class ConflictError(TruvixError):
    """The request collides with the current state of the resource."""

    status_code = HTTPStatus.CONFLICT
    error_code = "conflict"
    title = "Conflict"


class DomainValidationError(TruvixError):
    """Input satisfied the schema but violated a business rule."""

    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    error_code = "validation_failed"
    title = "Validation Failed"


class AuthenticationError(TruvixError):
    """The caller could not be identified, or the credentials were rejected."""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "authentication_failed"
    title = "Authentication Failed"


class AuthorizationError(TruvixError):
    """The caller is known but is not permitted to perform the action."""

    status_code = HTTPStatus.FORBIDDEN
    error_code = "permission_denied"
    title = "Permission Denied"


class AccountLockedError(AuthenticationError):
    """Authentication is temporarily blocked after repeated failed attempts."""

    error_code = "account_locked"
    title = "Account Temporarily Locked"

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        """Initialise the error.

        Args:
            message: Human-readable explanation safe to return to the caller.
            retry_after_seconds: Seconds the caller must wait before retrying.
        """
        super().__init__(message, details={"retry_after_seconds": retry_after_seconds})
        self.retry_after_seconds = retry_after_seconds


class RateLimitExceededError(TruvixError):
    """The caller exceeded the request budget for the current window."""

    status_code = HTTPStatus.TOO_MANY_REQUESTS
    error_code = "rate_limit_exceeded"
    title = "Rate Limit Exceeded"

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        """Initialise the error.

        Args:
            message: Human-readable explanation safe to return to the caller.
            retry_after_seconds: Seconds until the caller's budget resets.
        """
        super().__init__(message, details={"retry_after_seconds": retry_after_seconds})
        self.retry_after_seconds = retry_after_seconds


class QuotaExceededError(TruvixError):
    """The account has spent its allowance for a metered resource.

    Distinct from a rate limit: that says "too fast, wait a moment", this says
    "that is all you get today". The separate code lets a client offer an
    upgrade rather than a retry.
    """

    status_code = HTTPStatus.TOO_MANY_REQUESTS
    error_code = "quota_exceeded"
    title = "Quota Exceeded"

    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        """Initialise the error.

        Args:
            message: Human-readable explanation safe to return to the caller.
            retry_after_seconds: Seconds until the allowance renews, when it
                renews on a clock. A ceiling the user must make room under —
                a full garage — has no such time and omits it.
        """
        details = (
            {"retry_after_seconds": retry_after_seconds}
            if retry_after_seconds is not None
            else None
        )
        super().__init__(message, details=details)
        self.retry_after_seconds = retry_after_seconds


class ExternalServiceError(TruvixError):
    """A third-party dependency failed or returned an unusable response."""

    status_code = HTTPStatus.BAD_GATEWAY
    error_code = "external_service_error"
    title = "Upstream Service Error"

    def __init__(
        self,
        message: str,
        *,
        service: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialise the error.

        Args:
            message: Human-readable explanation safe to return to the caller.
            service: Identifier of the upstream dependency that failed.
            details: Structured, non-sensitive context describing the failure.
        """
        super().__init__(message, details={"service": service, **(details or {})})
        self.service = service


class ServiceUnavailableError(TruvixError):
    """The service cannot handle the request right now but may recover."""

    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    error_code = "service_unavailable"
    title = "Service Unavailable"
