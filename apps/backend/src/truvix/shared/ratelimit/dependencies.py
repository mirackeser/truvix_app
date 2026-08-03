"""FastAPI dependencies that enforce rate limits on individual endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from truvix.shared.config import Settings
from truvix.shared.dependencies import RedisDep, SettingsDep
from truvix.shared.errors import RateLimitExceededError
from truvix.shared.ratelimit.limiter import RateLimiter

_SECONDS_PER_MINUTE = 60

# Header a trusted reverse proxy uses to report the originating client address.
_FORWARDED_FOR_HEADER = "X-Forwarded-For"

_UNKNOWN_CLIENT = "unknown"


def get_rate_limiter(redis: RedisDep) -> RateLimiter:
    """Return a rate limiter for general endpoint throttling."""
    return RateLimiter(redis, fail_open=True)


def get_strict_rate_limiter(redis: RedisDep) -> RateLimiter:
    """Return a rate limiter that denies requests when Redis is unavailable.

    Used on authentication endpoints, where losing the limiter would otherwise
    hand an attacker unlimited password guesses.
    """
    return RateLimiter(redis, fail_open=False)


def client_identifier(request: Request) -> str:
    """Identify the caller for rate limiting purposes.

    Prefers the address reported by a trusted proxy, falling back to the
    immediate peer. Requests without any resolvable address share one bucket,
    which is intentionally conservative.
    """
    forwarded = request.headers.get(_FORWARDED_FOR_HEADER)
    if forwarded:
        # The originating client is the left-most entry in the chain.
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return _UNKNOWN_CLIENT


RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
StrictRateLimiterDep = Annotated[RateLimiter, Depends(get_strict_rate_limiter)]
ClientIdentifierDep = Annotated[str, Depends(client_identifier)]


async def enforce_auth_rate_limit(
    limiter: StrictRateLimiterDep,
    identifier: ClientIdentifierDep,
    settings: SettingsDep,
) -> None:
    """Throttle authentication attempts originating from one client address.

    Raises:
        RateLimitExceededError: When the caller has exhausted its budget.
    """
    await _enforce(
        limiter,
        scope="auth",
        identifier=identifier,
        limit=settings.rate_limit.auth_endpoint_requests_per_minute,
        settings=settings,
    )


async def _enforce(
    limiter: RateLimiter,
    *,
    scope: str,
    identifier: str,
    limit: int,
    settings: Settings,
) -> None:
    """Apply one rate limit check, raising when the budget is exhausted."""
    if not settings.rate_limit.enabled:
        return

    result = await limiter.check(
        scope=scope,
        identifier=identifier,
        limit=limit,
        window_seconds=_SECONDS_PER_MINUTE,
    )
    if not result.allowed:
        raise RateLimitExceededError(
            "Too many requests. Please wait before trying again.",
            retry_after_seconds=result.retry_after_seconds,
        )
