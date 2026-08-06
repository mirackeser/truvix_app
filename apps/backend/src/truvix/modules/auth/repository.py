"""Data access for refresh token sessions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CursorResult, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from truvix.modules.auth.models import RefreshToken


class RefreshTokenRepository:
    """Reads and writes refresh token records."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the repository.

        Args:
            session: The session whose transaction this repository participates in.
        """
        self._session = session

    async def get(self, token_id: uuid.UUID) -> RefreshToken | None:
        """Fetch a token by its identifier.

        Args:
            token_id: The token's ``jti``.
        """
        return await self._session.get(RefreshToken, token_id)

    def add(self, token: RefreshToken) -> None:
        """Stage a newly issued token for insertion.

        Args:
            token: The token record to persist.
        """
        self._session.add(token)

    async def flush(self) -> None:
        """Send pending changes to the database without committing.

        Needed when a later statement in the same transaction depends on rows
        staged earlier, such as pointing a rotated token at its replacement.
        """
        await self._session.flush()

    async def revoke(self, token: RefreshToken, *, at: datetime) -> None:
        """Mark a single token as revoked.

        Args:
            token: The token to invalidate.
            at: Timestamp to record as the revocation time.
        """
        if token.revoked_at is None:
            token.revoked_at = at
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, at: datetime) -> int:
        """Revoke every live session belonging to a user.

        Used both for "sign out everywhere" and as the response to detecting a
        replayed refresh token, where the safe assumption is that the account's
        entire session set is compromised.

        Args:
            user_id: Owner of the sessions.
            at: Timestamp to record as the revocation time.

        Returns:
            How many sessions were revoked.
        """
        statement = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=at)
        )
        result: CursorResult[None] = await self._session.execute(statement)  # type: ignore[assignment]
        await self._session.flush()
        return result.rowcount

    async def delete_expired(self, *, before: datetime) -> int:
        """Remove tokens that expired before the given time.

        Args:
            before: Cutoff; tokens expiring at or before this are removed.

        Returns:
            How many rows were deleted.
        """
        statement = delete(RefreshToken).where(RefreshToken.expires_at <= before)
        result: CursorResult[None] = await self._session.execute(statement)  # type: ignore[assignment]
        return result.rowcount
