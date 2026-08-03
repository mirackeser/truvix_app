"""Redis-backed fixed-window rate limiting.

The counter is incremented and given its expiry inside a single Lua script, so
the two operations are atomic. Doing them as separate round trips leaves a
window where a process crash between INCR and EXPIRE strands a key with no TTL,
permanently locking out whoever owns it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from redis.asyncio import Redis
from redis.exceptions import RedisError

from truvix.shared.logging import get_logger

_logger = get_logger(__name__)

_KEY_PREFIX: Final = "ratelimit"

# Returns the post-increment count and the key's remaining TTL. The expiry is
# set only on first increment so the window does not slide forward on every hit.
_INCREMENT_AND_EXPIRE: Final = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""

# TTL sentinel Redis returns for a key with no expiry set.
_NO_EXPIRY_TTL: Final = -1


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """Outcome of a rate limit check."""

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class RateLimiter:
    """Counts requests per caller within a fixed time window."""

    def __init__(self, redis: Redis, *, fail_open: bool = True) -> None:
        """Initialise the limiter.

        Args:
            redis: The Redis client backing the counters.
            fail_open: Whether to allow requests when Redis is unreachable.
                Defaults to allowing them, because a cache outage should not
                take the whole API down. Set to ``False`` on endpoints where
                unlimited attempts are more dangerous than an outage.
        """
        self._redis = redis
        self._fail_open = fail_open
        self._script = redis.register_script(_INCREMENT_AND_EXPIRE)

    async def check(
        self, *, scope: str, identifier: str, limit: int, window_seconds: int
    ) -> RateLimitResult:
        """Record one request and report whether it is within budget.

        Args:
            scope: Namespace for the limit, such as ``"auth"`` or ``"global"``.
            identifier: Who the budget belongs to, such as a user id or client IP.
            limit: Maximum requests permitted inside the window.
            window_seconds: Length of the window in seconds.

        Returns:
            The result of the check, including how long to wait when denied.
        """
        key = f"{_KEY_PREFIX}:{scope}:{identifier}"
        try:
            count, ttl = await self._script(keys=[key], args=[window_seconds])
        except RedisError as exc:
            _logger.warning("rate_limit_backend_unavailable", scope=scope, error=str(exc))
            if self._fail_open:
                return RateLimitResult(
                    allowed=True, limit=limit, remaining=limit, retry_after_seconds=0
                )
            return RateLimitResult(
                allowed=False, limit=limit, remaining=0, retry_after_seconds=window_seconds
            )

        # A missing TTL means the expiry was lost; treat the full window as the
        # wait so the caller is never told to retry immediately in a loop.
        retry_after = window_seconds if ttl == _NO_EXPIRY_TTL else max(int(ttl), 1)
        remaining = max(limit - int(count), 0)

        return RateLimitResult(
            allowed=int(count) <= limit,
            limit=limit,
            remaining=remaining,
            retry_after_seconds=retry_after,
        )

    async def reset(self, *, scope: str, identifier: str) -> None:
        """Clear a caller's counter, used after a successful authentication.

        Args:
            scope: Namespace the counter lives in.
            identifier: Who the counter belongs to.
        """
        try:
            await self._redis.delete(f"{_KEY_PREFIX}:{scope}:{identifier}")
        except RedisError as exc:
            _logger.warning("rate_limit_reset_failed", scope=scope, error=str(exc))
