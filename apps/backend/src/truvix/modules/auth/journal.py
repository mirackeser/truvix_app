"""Durable writes for security events that occur on failing requests.

A failed sign-in and a replayed refresh token both end with an exception, which
rolls back the request's transaction. Recording those events inside that same
transaction would therefore discard exactly the state that defends the account:
the lockout counter would never advance, and a detected token replay would not
actually revoke anything.

Every write here runs in its own transaction and commits independently of the
request, so the defence survives the failure that triggered it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import CursorResult, case, update

from truvix.modules.auth.models import RefreshToken
from truvix.modules.users.models import User
from truvix.shared.database import Database
from truvix.shared.logging import get_logger

_logger = get_logger(__name__)


class SecurityJournal:
    """Persists account protection state outside the request transaction."""

    def __init__(self, database: Database) -> None:
        """Initialise the journal.

        Args:
            database: Source of independent sessions.
        """
        self._database = database

    async def record_failed_login(
        self,
        user_id: uuid.UUID,
        *,
        max_attempts: int,
        lockout_minutes: int,
    ) -> None:
        """Count a failed attempt and lock the account once the limit is met.

        The counter is advanced in a single statement rather than read, modified
        and written back, so concurrent attempts from a distributed guesser
        cannot lose increments to a race.

        Args:
            user_id: The account that failed to authenticate.
            max_attempts: Failures tolerated before the account is locked.
            lockout_minutes: How long the lockout lasts.
        """
        next_attempts = User.failed_login_attempts + 1
        threshold_reached = next_attempts >= max_attempts
        locks_at = datetime.now(UTC) + timedelta(minutes=lockout_minutes)

        statement = (
            update(User)
            .where(User.id == user_id)
            .values(
                # Reset to zero on lockout so the next window starts clean.
                failed_login_attempts=case((threshold_reached, 0), else_=next_attempts),
                locked_until=case((threshold_reached, locks_at), else_=User.locked_until),
            )
        )

        async with self._database.transaction() as session:
            await session.execute(statement)

    async def revoke_all_sessions(self, user_id: uuid.UUID) -> int:
        """Revoke every live session belonging to an account.

        Args:
            user_id: Owner of the sessions.

        Returns:
            How many sessions were revoked.
        """
        statement = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

        async with self._database.transaction() as session:
            result: CursorResult[None] = await session.execute(statement)  # type: ignore[assignment]
            revoked = result.rowcount

        _logger.info("sessions_revoked", user_id=str(user_id), count=revoked)
        return int(revoked)
