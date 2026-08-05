"""Per-account consumption ceilings.

Rate limiting answers "how fast"; a quota answers "how much in total". They are
different defences against different failures. A per-minute limit does not stop
an account spending a month's AI budget over a day, and only a quota gives the
subscription tier something to mean.

Counters live in Redis keyed by account and calendar day, so the day's budget
resets without a scheduled job and without a row per user per day.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from redis.exceptions import RedisError

from truvix.modules.users.models import SubscriptionTier
from truvix.shared.config import QuotaSettings
from truvix.shared.errors import QuotaExceededError
from truvix.shared.logging import get_logger

_logger = get_logger(__name__)

_KEY_PREFIX: Final = "quota"

# The day a user's allowance resets on is their day, not UTC's. Someone in
# Istanbul who uses their last analysis at 01:00 should not have been charged
# it against the previous day.
_APP_TIMEZONE: Final = ZoneInfo("Europe/Istanbul")

# Counters outlive their day by a margin so a clock skew cannot expire one
# early, but are not kept indefinitely.
_COUNTER_TTL_SECONDS: Final = 60 * 60 * 36

_INCREMENT_AND_EXPIRE: Final = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


@dataclass(frozen=True, slots=True)
class QuotaStatus:
    """How much of an allowance is left."""

    used: int
    allowance: int

    @property
    def remaining(self) -> int:
        """How many more are permitted today."""
        return max(self.allowance - self.used, 0)

    @property
    def is_exhausted(self) -> bool:
        """Whether the allowance has been spent."""
        return self.used >= self.allowance


class QuotaService:
    """Counts and enforces what an account has consumed."""

    def __init__(self, redis: Redis, settings: QuotaSettings) -> None:
        """Initialise the service.

        Args:
            redis: Where the daily counters live.
            settings: The per-tier ceilings.
        """
        self._redis = redis
        self._settings = settings
        self._script = redis.register_script(_INCREMENT_AND_EXPIRE)

    def analyses_allowance(self, tier: SubscriptionTier) -> int:
        """How many analyses a tier may run in a day."""
        return (
            self._settings.premium_analyses_per_day
            if tier is SubscriptionTier.PREMIUM
            else self._settings.free_analyses_per_day
        )

    def vehicles_allowance(self, tier: SubscriptionTier) -> int:
        """How many vehicles a tier may keep in its garage."""
        return (
            self._settings.premium_vehicles
            if tier is SubscriptionTier.PREMIUM
            else self._settings.free_vehicles
        )

    async def analyses_today(self, user_id: uuid.UUID, tier: SubscriptionTier) -> QuotaStatus:
        """Report how much of today's analysis allowance is spent.

        Args:
            user_id: The account to report on.
            tier: The account's plan.
        """
        allowance = self.analyses_allowance(tier)
        try:
            raw = await self._redis.get(self._analysis_key(user_id))
        except RedisError as exc:
            _logger.warning("quota_read_failed", error=str(exc))
            return QuotaStatus(used=0, allowance=allowance)
        return QuotaStatus(used=int(raw or 0), allowance=allowance)

    async def consume_analysis(self, user_id: uuid.UUID, tier: SubscriptionTier) -> None:
        """Charge one analysis against today's allowance.

        Counting before the work rather than after means a run that fails
        halfway still costs its slot — the provider was already called, so the
        money was already spent.

        Args:
            user_id: The account running the analysis.
            tier: The account's plan.

        Raises:
            QuotaExceededError: When today's allowance is already spent, or
                when the counter cannot be reached.
        """
        allowance = self.analyses_allowance(tier)

        try:
            used = int(
                await self._script(keys=[self._analysis_key(user_id)], args=[_COUNTER_TTL_SECONDS])
            )
        except RedisError as exc:
            # Fails closed. An outage that pauses analyses is recoverable; one
            # that removes the only ceiling on AI spending is not.
            _logger.error("quota_backend_unavailable", error=str(exc))
            raise QuotaExceededError(
                "Analiz servisi şu anda kullanılamıyor. Lütfen kısa süre sonra tekrar deneyin.",
                retry_after_seconds=60,
            ) from exc

        if used > allowance:
            _logger.info("analysis_quota_exhausted", user_id=str(user_id), allowance=allowance)
            raise QuotaExceededError(
                f"Günlük {allowance} analiz hakkını kullandın. "
                "Yarın yenilenecek; Premium ile daha fazlasını yapabilirsin.",
                retry_after_seconds=self._seconds_until_reset(),
            )

    def assert_vehicle_allowed(self, *, current_count: int, tier: SubscriptionTier) -> None:
        """Check a new vehicle fits within the account's garage ceiling.

        Args:
            current_count: How many the garage already holds.
            tier: The account's plan.

        Raises:
            QuotaExceededError: When the garage is already full.
        """
        allowance = self.vehicles_allowance(tier)
        if current_count >= allowance:
            raise QuotaExceededError(
                f"Garajında en fazla {allowance} araç tutabilirsin. "
                "Yer açmak için bir aracı kaldır."
            )

    @staticmethod
    def _analysis_key(user_id: uuid.UUID) -> str:
        """The counter key for one account on the current local day."""
        today = datetime.now(UTC).astimezone(_APP_TIMEZONE).date()
        return f"{_KEY_PREFIX}:analyses:{user_id}:{today.isoformat()}"

    @staticmethod
    def _seconds_until_reset() -> int:
        """How long until the allowance renews, for the Retry-After header."""
        now = datetime.now(UTC).astimezone(_APP_TIMEZONE)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return max(int((tomorrow - now).total_seconds()), 1)
