"""Registering devices and pushing notifications to them.

A device token is not a secret and not an identity: it identifies an
installation, it rotates whenever iOS decides to, and the same physical phone
can hold tokens for several accounts. So registration is idempotent on the
token, and a token that turns up under a new account moves rather than
duplicating — otherwise signing out and back in as somebody else would send
their notifications to the previous occupant.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from truvix.modules.notifications.models import DeviceToken, Notification
from truvix.shared.logging import get_logger
from truvix.shared.push import DeliveryOutcome, PushMessage, PushSender

_logger = get_logger(__name__)


class DeviceRegistry:
    """Keeps track of where an account's notifications should go."""

    def __init__(self, session: AsyncSession, sender: PushSender) -> None:
        """Initialise the registry.

        Args:
            session: The session whose transaction this participates in.
            sender: Delivers the notification to Apple.
        """
        self._session = session
        self._sender = sender

    async def register(self, *, user_id: uuid.UUID, token: str) -> DeviceToken:
        """Record that an account's notifications should reach this device.

        Idempotent, and safe when the device previously belonged to another
        account: the row moves rather than being duplicated, so the previous
        occupant stops receiving notifications meant for somebody else.

        Args:
            user_id: The signed-in account.
            token: The APNs device token, as iOS reported it.

        Returns:
            The stored registration.
        """
        existing = await self._session.scalar(select(DeviceToken).where(DeviceToken.token == token))
        now = datetime.now(UTC)

        if existing is not None:
            if existing.user_id != user_id:
                _logger.info("device_reassigned", token_suffix=token[-8:])
            existing.user_id = user_id
            existing.last_seen_at = now
            await self._session.flush()
            return existing

        device = DeviceToken(user_id=user_id, token=token, last_seen_at=now)
        self._session.add(device)
        await self._session.flush()
        _logger.info("device_registered", user_id=str(user_id))
        return device

    async def unregister(self, *, token: str) -> None:
        """Stop sending to a device.

        Takes no account: signing out should stop notifications whether or not
        the token was ever registered, and a caller that had to prove ownership
        of a token it is discarding would have to keep it around to do so.

        Args:
            token: The device token to forget.
        """
        await self._session.execute(delete(DeviceToken).where(DeviceToken.token == token))

    async def push(self, notification: Notification, *, unread: int) -> int:
        """Send one notification to every device the account has registered.

        Delivery is best effort by design. The notification is already recorded
        and readable in the app, so a push that does not arrive is a missed
        prompt rather than lost data — and losing a price-drop alert is not a
        reason to lose the price drop.

        Args:
            notification: The notification to deliver.
            unread: The account's unread count, shown on the app icon.

        Returns:
            How many devices accepted it.
        """
        devices = (
            await self._session.scalars(
                select(DeviceToken).where(DeviceToken.user_id == notification.user_id)
            )
        ).all()
        if not devices:
            return 0

        message = PushMessage(
            title=notification.title,
            body=notification.body,
            badge=unread,
            data=self._deep_link(notification),
        )

        delivered = 0
        stale: list[str] = []
        for device in devices:
            outcome = await self._sender.send(message, device_token=device.token)
            if outcome is DeliveryOutcome.DELIVERED:
                delivered += 1
            elif outcome is DeliveryOutcome.UNREGISTERED:
                # Apple says this token is dead. Keeping it means paying for a
                # rejected request on every future notification, forever.
                stale.append(device.token)

        for token in stale:
            await self.unregister(token=token)

        if stale:
            _logger.info("stale_devices_removed", count=len(stale))
        return delivered

    @staticmethod
    def _deep_link(notification: Notification) -> dict[str, str]:
        """What the app needs to open the right screen on a tap."""
        data = {
            "notification_id": str(notification.id),
            "event_type": notification.event_type,
        }
        if notification.vehicle_id is not None:
            data["vehicle_id"] = str(notification.vehicle_id)
        return data
