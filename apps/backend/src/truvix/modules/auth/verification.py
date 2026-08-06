"""Email verification: issuing, sending and consuming a one-time link.

The token is stored as a SHA-256 digest rather than in the clear. A database
that leaks is bad enough without also handing over the ability to verify every
address in it, and the token is high-entropy random rather than a password, so a
fast digest is the right tool — Argon2 exists to make guessing a human-chosen
secret slow, which is not the threat here.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from truvix.modules.auth.models import EmailVerificationToken
from truvix.modules.users.models import User
from truvix.shared.config import EmailSettings
from truvix.shared.email import Email, EmailSender
from truvix.shared.errors import ConflictError, DomainValidationError
from truvix.shared.logging import get_logger

_logger = get_logger(__name__)

# 32 bytes of randomness, URL-safe. Long enough that guessing is not a strategy
# even without a rate limit, and short enough to survive being pasted by hand.
_TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    """Reduce a token to what is safe to store."""
    return hashlib.sha256(token.encode()).hexdigest()


class EmailVerificationService:
    """Issues and consumes email verification links."""

    def __init__(
        self,
        session: AsyncSession,
        sender: EmailSender,
        settings: EmailSettings,
    ) -> None:
        """Initialise the service.

        Args:
            session: The session whose transaction this participates in.
            sender: Where the message goes.
            settings: Link lifetime and the address it points at.
        """
        self._session = session
        self._sender = sender
        self._settings = settings

    async def send_verification(self, user: User) -> bool:
        """Issue a fresh link and mail it.

        Any earlier token for the account is discarded first, so a link that was
        emailed and then superseded cannot still be used. Somebody who asks for a
        new link is usually saying the old one did not arrive.

        Args:
            user: The account to verify.

        Returns:
            Whether the message was accepted for delivery.

        Raises:
            ConflictError: If the address is already verified.
        """
        if user.is_email_verified:
            raise ConflictError("Bu e-posta adresi zaten doğrulanmış.")

        # Issuing a link is a fine moment to sweep: there is no scheduler in
        # this deployment, the expiry index makes the sweep cheap, and a table
        # of tokens nobody can use should not grow without bound.
        await self.purge_expired()

        await self._session.execute(
            delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
        )

        token = secrets.token_urlsafe(_TOKEN_BYTES)
        self._session.add(
            EmailVerificationToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC)
                + timedelta(hours=self._settings.verification_ttl_hours),
            )
        )
        await self._session.flush()

        delivered = await self._sender.send(self._compose(user, token))
        _logger.info("verification_requested", user_id=str(user.id), delivered=delivered)
        return delivered

    async def verify(self, token: str) -> User:
        """Consume a link and mark the address verified.

        Args:
            token: The token from the link.

        Returns:
            The account, now verified.

        Raises:
            DomainValidationError: If the token is unknown, spent or expired.
                All three answer identically, so a caller cannot learn which
                tokens exist by the shape of the refusal.
        """
        record = await self._session.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == hash_token(token)
            )
        )
        if record is None or record.expires_at <= datetime.now(UTC):
            _logger.info("verification_rejected", known=record is not None)
            raise DomainValidationError(
                "Doğrulama bağlantısı geçersiz veya süresi dolmuş. Yeni bir bağlantı iste."
            )

        user = await self._session.get(User, record.user_id)
        if user is None:
            raise DomainValidationError("Doğrulama bağlantısı geçersiz veya süresi dolmuş.")

        if not user.is_email_verified:
            user.email_verified_at = datetime.now(UTC)

        # Single use: the link is now spent whether or not it changed anything.
        await self._session.delete(record)
        await self._session.flush()

        _logger.info("email_verified", user_id=str(user.id))
        return user

    async def purge_expired(self) -> int:
        """Delete tokens that can no longer be used.

        Returns:
            How many were removed.
        """
        result = await self._session.execute(
            delete(EmailVerificationToken).where(
                EmailVerificationToken.expires_at <= datetime.now(UTC)
            )
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def _compose(self, user: User, token: str) -> Email:
        """Write the message."""
        link = f"{str(self._settings.verification_base_url).rstrip('/')}?token={token}"
        hours = self._settings.verification_ttl_hours
        name = user.full_name.split()[0] if user.full_name else "Merhaba"

        return Email(
            to=user.email,
            subject="Truvix hesabını doğrula",
            body=(
                f"{name},\n\n"
                "Truvix hesabını doğrulamak için aşağıdaki bağlantıyı aç:\n\n"
                f"{link}\n\n"
                f"Bağlantı {hours} saat geçerli. Bu hesabı sen açmadıysan "
                "bu e-postayı yok sayabilirsin.\n\n"
                "Truvix"
            ),
        )
