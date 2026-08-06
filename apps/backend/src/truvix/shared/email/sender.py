"""Sending transactional email.

Kept behind a protocol with an SMTP implementation rather than a vendor's SDK.
Every provider worth using speaks SMTP, so the choice of provider becomes a
configuration change rather than a code change, and a deployment with nothing
configured degrades to logging instead of failing.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol, runtime_checkable

import anyio

from truvix.shared.config import EmailSettings
from truvix.shared.logging import get_logger

_logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Email:
    """One message to one person."""

    to: str
    subject: str
    #: The plain-text body. Every client renders it, and it cannot carry a
    #: tracking pixel or a payload, which is the right default for a message
    #: whose only job is to carry a link.
    body: str


@runtime_checkable
class EmailSender(Protocol):
    """Delivers a message, or reports that it could not."""

    async def send(self, message: Email) -> bool:
        """Send one message.

        Args:
            message: What to send.

        Returns:
            Whether it was handed to a mail server.
        """
        ...


class SMTPEmailSender:
    """Sends through an SMTP server."""

    def __init__(self, settings: EmailSettings) -> None:
        """Initialise the sender.

        Args:
            settings: Where to connect and who to send as.

        Raises:
            ValueError: If no host is configured. Built through
                :func:`build_email_sender`, which only reaches here once one is,
                so this guards against a future caller rather than a user.
        """
        if settings.host is None:
            raise ValueError("SMTPEmailSender needs a host; use build_email_sender.")
        self._host = settings.host
        self._settings = settings

    async def send(self, message: Email) -> bool:
        """Send one message, reporting failure rather than raising.

        A failure here must not fail the request that caused it: somebody
        registering an account has already registered, and the verification mail
        can be asked for again. Raising would undo the registration for a reason
        that has nothing to do with it.
        """
        try:
            # smtplib is blocking, so it runs off the event loop rather than
            # stalling every other request for the length of an SMTP round trip.
            await anyio.to_thread.run_sync(self._send_blocking, message)
        except Exception:
            _logger.exception("email_send_failed", to=_redact(message.to))
            return False

        _logger.info("email_sent", to=_redact(message.to), subject=message.subject)
        return True

    def _send_blocking(self, message: Email) -> None:
        """Do the actual SMTP conversation."""
        import smtplib

        payload = EmailMessage()
        payload["From"] = self._settings.from_address
        payload["To"] = message.to
        payload["Subject"] = message.subject
        payload.set_content(message.body)

        settings = self._settings
        if settings.use_tls:
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                self._host, settings.port, timeout=settings.timeout_seconds
            )
        else:
            client = smtplib.SMTP(self._host, settings.port, timeout=settings.timeout_seconds)

        with client:
            if settings.use_starttls:
                client.starttls(context=ssl.create_default_context())
            if settings.username and settings.password:
                client.login(settings.username, settings.password.get_secret_value())
            client.send_message(payload)


class LoggingEmailSender:
    """Writes the message to the log instead of sending it.

    Used when no mail server is configured. Development and testing need the
    link that would have been mailed, and printing it is more useful there than
    an outbound connection would be. It reports success because, for its
    purposes, the message did arrive somewhere a developer can read it.
    """

    async def send(self, message: Email) -> bool:
        """Record the message rather than delivering it."""
        _logger.info(
            "email_not_configured_logging_instead",
            to=_redact(message.to),
            subject=message.subject,
            body=message.body,
        )
        return True


def _redact(address: str) -> str:
    """Reduce an address to something safe to keep in a log.

    Logs outlive the reason they were written and get shipped to places the
    person who signed up never agreed to. The domain is enough to diagnose a
    delivery problem; the local part is not needed for it.
    """
    _, _, domain = address.partition("@")
    return f"***@{domain}" if domain else "***"


def build_email_sender(settings: EmailSettings) -> EmailSender:
    """Choose the sender this deployment can actually use.

    Args:
        settings: The mail configuration, which may be empty.
    """
    if not settings.configured:
        return LoggingEmailSender()
    return SMTPEmailSender(settings)
