"""Resetting a forgotten password.

The token is stored as a SHA-256 digest and lives in its own table rather than
sharing one with email verification. Two links that grant different things
should not be interchangeable by a column value somebody could get wrong: a
verification token can never be presented here, because it is not in this table.

Two rules shape everything else:

- **Asking about an address tells you nothing.** The endpoint answers the same
  way whether or not an account exists, so it cannot be used to find out who has
  signed up.
- **A reset ends every session.** Somebody resetting their password may be doing
  it because a stranger has their account. Leaving that stranger's session alive
  would make the reset theatre.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from truvix.modules.auth.models import PasswordResetToken
from truvix.modules.auth.repository import RefreshTokenRepository
from truvix.modules.users.models import User
from truvix.shared.config import EmailSettings
from truvix.shared.email import Email, EmailSender
from truvix.shared.errors import DomainValidationError
from truvix.shared.logging import get_logger
from truvix.shared.security import PasswordHasherService

_logger = get_logger(__name__)

_TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    """Reduce a token to what is safe to store."""
    return hashlib.sha256(token.encode()).hexdigest()


class PasswordResetService:
    """Issues and consumes password reset links."""

    def __init__(
        self,
        session: AsyncSession,
        sender: EmailSender,
        settings: EmailSettings,
        hasher: PasswordHasherService,
        sessions: RefreshTokenRepository,
    ) -> None:
        """Initialise the service.

        Args:
            session: The session whose transaction this participates in.
            sender: Where the message goes.
            settings: Link lifetime and the address it points at.
            hasher: Hashes the replacement password.
            sessions: Used to revoke every session once the password changes.
        """
        self._session = session
        self._sender = sender
        self._settings = settings
        self._hasher = hasher
        self._sessions = sessions

    async def request_reset(self, email: str) -> None:
        """Send a reset link, if there is an account to send one to.

        Returns nothing either way, and the caller must answer identically in
        both cases. An endpoint that says "no such account" is a way to test
        whether somebody has signed up, which is not ours to disclose — the
        addresses would be a list of people who own a car and are thinking of
        selling it.

        Args:
            email: The address somebody typed into the form.
        """
        user = await self._session.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            _logger.info("password_reset_requested_for_unknown_address")
            return

        # Issuing a link is a fine moment to sweep: there is no scheduler in
        # this deployment, the expiry index makes the sweep cheap, and a table
        # of tokens nobody can use should not grow without bound.
        await self.purge_expired()

        await self._session.execute(
            delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )

        token = secrets.token_urlsafe(_TOKEN_BYTES)
        self._session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC)
                + timedelta(hours=self._settings.password_reset_ttl_hours),
            )
        )
        await self._session.flush()

        delivered = await self._sender.send(self._compose(user, token))
        _logger.info("password_reset_requested", user_id=str(user.id), delivered=delivered)

    async def reset(self, *, token: str, new_password: str) -> User:
        """Set a new password and end every session.

        Args:
            token: The token from the link.
            new_password: The replacement password, already validated.

        Returns:
            The account, with its new password.

        Raises:
            DomainValidationError: If the token is unknown, spent or expired.
                All three answer alike, so the refusal cannot be used to learn
                which tokens exist.
        """
        record = await self._session.scalar(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token))
        )
        now = datetime.now(UTC)
        if record is None or record.expires_at <= now:
            _logger.info("password_reset_rejected", known=record is not None)
            raise DomainValidationError(
                "Sıfırlama bağlantısı geçersiz veya süresi dolmuş. Yeni bir bağlantı iste."
            )

        user = await self._session.get(User, record.user_id)
        if user is None:
            raise DomainValidationError("Sıfırlama bağlantısı geçersiz veya süresi dolmuş.")

        user.password_hash = self._hasher.hash(new_password)

        # Somebody may be resetting because a stranger is in their account.
        # Leaving that session alive would make the reset pointless.
        revoked = await self._sessions.revoke_all_for_user(user.id, at=now)

        # Refresh tokens are rows and can be revoked; an access token is a
        # signed JWT that nothing checks against the database, so revoking the
        # sessions would still leave a stranger half an hour of access. This
        # closes that window.
        user.tokens_invalid_before = now

        # A locked-out account has just proved it reads the address it signed up
        # with, which is a stronger claim than waiting out the lockout. Leaving
        # the lock in place would mean a successful reset still could not sign in.
        user.failed_login_attempts = 0
        user.locked_until = None

        # Using the link proves the same thing the verification link proves, so
        # asking for that separately afterwards would be asking twice.
        if not user.is_email_verified:
            user.email_verified_at = now

        await self._session.delete(record)
        await self._session.flush()

        _logger.info("password_reset_completed", user_id=str(user.id), sessions_revoked=revoked)
        return user

    async def purge_expired(self) -> int:
        """Delete tokens that can no longer be used.

        Returns:
            How many were removed.
        """
        result = await self._session.execute(
            delete(PasswordResetToken).where(PasswordResetToken.expires_at <= datetime.now(UTC))
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def _compose(self, user: User, token: str) -> Email:
        """Write the message."""
        link = f"{str(self._settings.password_reset_base_url).rstrip('/')}?token={token}"
        hours = self._settings.password_reset_ttl_hours
        name = user.full_name.split()[0] if user.full_name else "Merhaba"

        return Email(
            to=user.email,
            subject="Truvix şifreni sıfırla",
            body=(
                f"{name},\n\n"
                "Şifreni sıfırlamak için aşağıdaki bağlantıyı aç:\n\n"
                f"{link}\n\n"
                f"Bağlantı {hours} saat geçerli ve yalnızca bir kez kullanılabilir.\n\n"
                "Bu isteği sen yapmadıysan bu e-postayı yok sayabilirsin; "
                "şifren değişmez. Ancak bunu beklemiyorsan hesabına giriş yapıp "
                "şifreni değiştirmeni öneririz.\n\n"
                "Truvix"
            ),
        )
