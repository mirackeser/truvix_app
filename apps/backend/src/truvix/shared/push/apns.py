"""Delivering push notifications through Apple's service.

Token-based authentication rather than certificates: a p8 signing key does not
expire, where a push certificate does and takes the notifications down with it
on a day nobody is watching. The provider token is a short-lived JWT signed with
that key, cached and reissued on Apple's schedule.

The whole thing sits behind a protocol with a logging implementation, matching
how mail is handled: a deployment with no key configured writes what it would
have sent instead of failing, so development and tests need no Apple account.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

import httpx
import jwt

from truvix.shared.config import ApnsSettings
from truvix.shared.logging import get_logger

_logger = get_logger(__name__)

# Apple reissues provider tokens no more often than every 20 minutes and rejects
# any older than an hour. Refreshing at 45 minutes sits comfortably inside both.
_TOKEN_LIFETIME_SECONDS = 45 * 60

_SANDBOX_HOST = "https://api.sandbox.push.apple.com"
_PRODUCTION_HOST = "https://api.push.apple.com"

# Apple's own ceiling for a notification payload.
MAX_PAYLOAD_BYTES = 4096


class DeliveryOutcome(StrEnum):
    """What became of one notification."""

    DELIVERED = "delivered"
    #: The device no longer accepts notifications; its token should be removed.
    UNREGISTERED = "unregistered"
    #: A transient failure. The notification is lost, but the token is fine.
    FAILED = "failed"
    #: Nothing was sent because no credentials are configured.
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class PushMessage:
    """One notification, as the device will receive it."""

    title: str
    body: str
    #: Rendered on the app icon. The count is computed by the caller, because
    #: only it knows how many notifications are unread.
    badge: int | None = None
    #: Travels with the notification so a tap can open the right screen.
    data: dict[str, str] | None = None

    def payload(self) -> dict[str, Any]:
        """Build the APNs payload."""
        alert: dict[str, Any] = {"title": self.title, "body": self.body}
        aps: dict[str, Any] = {"alert": alert, "sound": "default"}
        if self.badge is not None:
            aps["badge"] = self.badge

        payload: dict[str, Any] = {"aps": aps}
        if self.data:
            payload.update(self.data)
        return payload


@runtime_checkable
class PushSender(Protocol):
    """Delivers a notification to one device."""

    async def send(self, message: PushMessage, *, device_token: str) -> DeliveryOutcome:
        """Send one notification.

        Args:
            message: What to show.
            device_token: The device to send it to.

        Returns:
            What became of it.
        """
        ...


class ApnsPushSender:
    """Sends through Apple Push Notification service."""

    def __init__(self, settings: ApnsSettings, client: httpx.AsyncClient) -> None:
        """Initialise the sender.

        Args:
            settings: Signing key and identifiers.
            client: An HTTP/2 client. APNs speaks nothing else, and a client
                without HTTP/2 fails with an error that does not say so.

        Raises:
            ValueError: If the settings are incomplete. Built through
                :func:`build_push_sender`, which only reaches here once they
                are, so this guards a future caller rather than a user.
        """
        if not settings.configured:
            raise ValueError("ApnsPushSender needs credentials; use build_push_sender.")
        self._settings = settings
        self._client = client
        self._host = _SANDBOX_HOST if settings.use_sandbox else _PRODUCTION_HOST
        self._token: str | None = None
        self._token_issued_at = 0.0

    async def send(self, message: PushMessage, *, device_token: str) -> DeliveryOutcome:
        """Send one notification, reporting failure rather than raising.

        A push that does not arrive must not fail the request that produced it:
        the notification is already recorded and readable in the app, and losing
        the price-drop alert is not a reason to lose the price drop.
        """
        body = json.dumps(message.payload(), separators=(",", ":")).encode()
        if len(body) > MAX_PAYLOAD_BYTES:
            # Truncating silently would ship a notification missing the part
            # that mattered; Apple would reject it anyway.
            _logger.error("push_payload_too_large", size=len(body))
            return DeliveryOutcome.FAILED

        try:
            response = await self._client.post(
                f"{self._host}/3/device/{device_token}",
                content=body,
                headers={
                    "authorization": f"bearer {self._provider_token()}",
                    "apns-topic": self._settings.bundle_id or "",
                    "apns-push-type": "alert",
                    "apns-priority": "10",
                    "content-type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            _logger.warning("push_send_failed", error=str(exc))
            return DeliveryOutcome.FAILED

        return self._interpret(response, device_token=device_token)

    def _interpret(self, response: httpx.Response, *, device_token: str) -> DeliveryOutcome:
        """Turn Apple's answer into an outcome."""
        if response.is_success:
            return DeliveryOutcome.DELIVERED

        reason = ""
        try:
            reason = str(response.json().get("reason", ""))
        except ValueError:
            reason = response.text[:200]

        # These two mean the token is dead rather than the send being unlucky:
        # the app was deleted, or the token belongs to a different environment.
        if response.status_code in {400, 410} and reason in {
            "BadDeviceToken",
            "Unregistered",
            "DeviceTokenNotForTopic",
        }:
            _logger.info("push_token_rejected", reason=reason, token_suffix=device_token[-8:])
            return DeliveryOutcome.UNREGISTERED

        _logger.warning("push_rejected", status=response.status_code, reason=reason)
        return DeliveryOutcome.FAILED

    def _provider_token(self) -> str:
        """The signed provider token, reissued when it ages out."""
        now = time.time()
        if self._token is not None and now - self._token_issued_at < _TOKEN_LIFETIME_SECONDS:
            return self._token

        self._token = jwt.encode(
            {"iss": self._settings.team_id, "iat": int(now)},
            self._settings.signing_key,
            algorithm="ES256",
            headers={"kid": self._settings.key_id},
        )
        self._token_issued_at = now
        return self._token


class LoggingPushSender:
    """Writes the notification to the log instead of sending it.

    Used when no signing key is configured, so development and the test suite
    need no Apple account. Reports ``SKIPPED`` rather than ``DELIVERED``: the
    caller must not record a delivery that never happened.
    """

    async def send(self, message: PushMessage, *, device_token: str) -> DeliveryOutcome:
        """Record the notification rather than delivering it."""
        _logger.info(
            "push_not_configured_logging_instead",
            title=message.title,
            body=message.body,
            token_suffix=device_token[-8:],
        )
        return DeliveryOutcome.SKIPPED


def build_push_sender(settings: ApnsSettings, client: httpx.AsyncClient) -> PushSender:
    """Choose the sender this deployment can actually use.

    Args:
        settings: The push configuration, which may be empty.
        client: The HTTP/2 client to send over.
    """
    if not settings.configured:
        return LoggingPushSender()
    return ApnsPushSender(settings, client)
