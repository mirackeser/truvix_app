"""Deleting an account and everything that belongs to it.

Apple requires an app that lets somebody create an account to let them delete it
from inside the app (App Store Review Guideline 5.1.1(v)), and Turkish data
protection law gives the same right from the other direction. Neither is served
by a flag that hides a row: this removes the record and the files behind it.

What it cannot do is cancel the subscription. Apple owns that relationship, and
only the customer can end it from their Apple ID settings — so the caller is
told, rather than left to discover it on the next renewal.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truvix.modules.analysis.models import AnalysisPhoto, VehicleAnalysis
from truvix.modules.users.models import User
from truvix.modules.vehicles.models import Vehicle
from truvix.shared.errors import AuthenticationError, NotFoundError
from truvix.shared.logging import get_logger
from truvix.shared.security import PasswordHasherService
from truvix.shared.storage import FileStorage

_logger = get_logger(__name__)


class AccountDeletionService:
    """Erases an account, its data and its uploaded files."""

    def __init__(
        self,
        session: AsyncSession,
        storage: FileStorage,
        hasher: PasswordHasherService,
    ) -> None:
        """Initialise the service.

        Args:
            session: The session whose transaction this participates in.
            storage: Where uploaded photographs live.
            hasher: Used to check the password confirming the deletion.
        """
        self._session = session
        self._storage = storage
        self._hasher = hasher

    async def delete(self, *, user_id: uuid.UUID, password: str) -> None:
        """Delete an account after confirming the password.

        The password is required even though the caller already holds a valid
        access token. A token can be borrowed from an unlocked phone; this is
        the one action in the application that cannot be undone, so it asks the
        person to prove they are the account holder rather than merely holding
        the handset.

        Files are removed before the rows that name them. Doing it the other way
        round loses the keys if the transaction commits and the file sweep then
        fails, leaving photographs on disk that nothing points to — the opposite
        of what somebody deleting their account asked for.

        Args:
            user_id: The account to delete.
            password: The account's password, as confirmation.

        Raises:
            NotFoundError: If the account no longer exists.
            AuthenticationError: If the password does not match.
        """
        user = await self._session.get(User, user_id)
        if user is None:
            raise NotFoundError.for_resource("User", user_id)

        if not self._hasher.verify(password, user.password_hash):
            _logger.warning("account_deletion_rejected", user_id=str(user_id))
            raise AuthenticationError("Şifre doğrulanamadı. Hesap silinmedi.")

        removed = await self._remove_uploaded_files(user_id)

        # Every table that references a user does so with ON DELETE CASCADE, so
        # the rows go with it: vehicles, analyses, findings, photographs,
        # conversations, notifications, sessions and entitlements.
        await self._session.delete(user)
        await self._session.flush()

        _logger.info("account_deleted", user_id=str(user_id), files_removed=removed)

    async def _remove_uploaded_files(self, user_id: uuid.UUID) -> int:
        """Delete every photograph the account uploaded.

        Args:
            user_id: The account whose files should go.

        Returns:
            How many objects were removed.
        """
        keys = (
            await self._session.scalars(
                select(AnalysisPhoto.storage_key)
                .join(VehicleAnalysis, AnalysisPhoto.analysis_id == VehicleAnalysis.id)
                .join(Vehicle, VehicleAnalysis.vehicle_id == Vehicle.id)
                .where(Vehicle.user_id == user_id)
            )
        ).all()

        for key in keys:
            # Missing objects are ignored: a file already gone is the state
            # being asked for, and refusing to continue would strand the rest.
            self._storage.delete(key)

        return len(keys)
