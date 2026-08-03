"""Authentication business logic.

Three security properties are enforced here and are worth stating explicitly,
because each one is easy to lose in a later refactor:

1. Sign-in takes the same work whether or not the address exists, so response
   timing cannot be used to enumerate registered users.
2. Repeated failures lock an account for a cooling-off period, which bounds how
   fast an attacker can guess even if rate limiting is bypassed.
3. Refresh tokens rotate on every use, and presenting an already-rotated token
   revokes every session for that account. A replayed token means two parties
   hold the same credential, and the only safe reading is that one is an
   attacker.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from truvix.modules.auth.journal import SecurityJournal
from truvix.modules.auth.models import USER_AGENT_MAX_LENGTH, RefreshToken
from truvix.modules.auth.repository import RefreshTokenRepository
from truvix.modules.users.models import User
from truvix.modules.users.repository import UserRepository
from truvix.shared.config import SecuritySettings
from truvix.shared.errors import (
    AccountLockedError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
)
from truvix.shared.logging import get_logger
from truvix.shared.security import IssuedToken, PasswordHasherService, TokenService, TokenType

_logger = get_logger(__name__)

# Hashed once at import so that authenticating a non-existent address performs
# the same Argon2 work as a real one, keeping response times indistinguishable.
_TIMING_EQUALISER_PASSWORD = "truvix-timing-equaliser"  # noqa: S105 - not a credential

_SECONDS_PER_MINUTE = 60


@dataclass(frozen=True, slots=True)
class SessionContext:
    """Details about the client establishing or continuing a session."""

    user_agent: str | None = None
    ip_address: str | None = None

    def truncated_user_agent(self) -> str | None:
        """The user agent trimmed to the column's capacity."""
        if self.user_agent is None:
            return None
        return self.user_agent[:USER_AGENT_MAX_LENGTH]


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    """An authenticated account and the tokens issued for it."""

    user: User
    access_token: IssuedToken
    refresh_token: IssuedToken
    access_token_ttl_seconds: int


class AuthService:
    """Registers accounts, authenticates credentials and rotates sessions."""

    def __init__(
        self,
        *,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        password_hasher: PasswordHasherService,
        token_service: TokenService,
        settings: SecuritySettings,
        journal: SecurityJournal,
    ) -> None:
        """Initialise the service with its collaborators.

        Args:
            users: Access to user records.
            refresh_tokens: Access to refresh token records.
            password_hasher: Hashing and verification of passwords.
            token_service: Issuing and verification of JWTs.
            settings: Lockout thresholds and token lifetimes.
            journal: Durable writes for events that end in a failed request.
        """
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._password_hasher = password_hasher
        self._token_service = token_service
        self._settings = settings
        self._journal = journal
        self._timing_equaliser_hash = password_hasher.hash(_TIMING_EQUALISER_PASSWORD)

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        phone_number: str | None,
        context: SessionContext,
    ) -> AuthenticatedSession:
        """Create an account and start a session for it.

        Args:
            email: The address to register, in any casing.
            password: The plaintext password, already length-validated.
            full_name: The account holder's display name.
            phone_number: Optional contact number in E.164 form.
            context: Details about the registering client.

        Returns:
            The new account with its first token pair.

        Raises:
            ConflictError: If the address or phone number is already registered.
        """
        normalised_email = self.normalise_email(email)

        if await self._users.email_is_taken(normalised_email):
            raise ConflictError("An account with this email address already exists.")
        if phone_number is not None and await self._users.phone_is_taken(phone_number):
            raise ConflictError("An account with this phone number already exists.")

        user = User(
            email=normalised_email,
            password_hash=self._password_hasher.hash(password),
            full_name=full_name,
            phone_number=phone_number,
        )
        self._users.add(user)
        await self._users.flush()

        _logger.info("user_registered", user_id=str(user.id))
        return self._start_session(user, context=context)

    async def authenticate(
        self, *, email: str, password: str, context: SessionContext
    ) -> AuthenticatedSession:
        """Verify credentials and start a session.

        Args:
            email: The address to authenticate, in any casing.
            password: The plaintext password to verify.
            context: Details about the signing-in client.

        Returns:
            The authenticated account with a fresh token pair.

        Raises:
            AuthenticationError: If the credentials do not match an account.
            AccountLockedError: If the account is in its lockout window.
            AuthorizationError: If the account is suspended.
        """
        normalised_email = self.normalise_email(email)
        user = await self._users.get_by_email(normalised_email)
        now = datetime.now(UTC)

        if user is None:
            # Perform equivalent hashing work so that an unknown address costs
            # the same as a known one, then fail identically.
            self._password_hasher.verify(password, self._timing_equaliser_hash)
            _logger.info("login_failed", reason="unknown_email")
            raise AuthenticationError("Email address or password is incorrect.")

        self._assert_not_locked(user, now=now)

        if not self._password_hasher.verify(password, user.password_hash):
            await self._journal.record_failed_login(
                user.id,
                max_attempts=self._settings.max_failed_login_attempts,
                lockout_minutes=self._settings.account_lockout_minutes,
            )
            _logger.info("login_failed", reason="bad_password", user_id=str(user.id))
            raise AuthenticationError("Email address or password is incorrect.")

        if not user.status.can_authenticate:
            _logger.warning("login_blocked", user_id=str(user.id), status=user.status.value)
            raise AuthorizationError("This account is not permitted to sign in.")

        self._upgrade_password_hash_if_needed(user, password)

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now

        _logger.info("login_succeeded", user_id=str(user.id))
        return self._start_session(user, context=context)

    async def refresh(self, *, refresh_token: str, context: SessionContext) -> AuthenticatedSession:
        """Exchange a refresh token for a new pair, rotating the old one.

        Args:
            refresh_token: The encoded refresh JWT presented by the client.
            context: Details about the refreshing client.

        Returns:
            The account with a newly issued token pair.

        Raises:
            AuthenticationError: If the token is invalid, expired, unknown, or
                has already been rotated.
            AuthorizationError: If the owning account may no longer sign in.
        """
        claims = self._token_service.decode(refresh_token, expected_type=TokenType.REFRESH)
        now = datetime.now(UTC)

        stored = await self._refresh_tokens.get(claims.token_id)
        if stored is None:
            _logger.warning("refresh_rejected", reason="unknown_token", user_id=str(claims.subject))
            raise AuthenticationError("The provided token is invalid or has expired.")

        if stored.is_revoked:
            # The signature was valid, so this token was genuinely issued to
            # this account and has since been rotated. Someone is replaying it.
            # The revocation is journalled independently, because this request
            # ends in an exception that would otherwise roll it back.
            revoked = await self._journal.revoke_all_sessions(stored.user_id)
            _logger.warning(
                "refresh_token_reuse_detected",
                user_id=str(stored.user_id),
                sessions_revoked=revoked,
            )
            raise AuthenticationError("The provided token is invalid or has expired.")

        if stored.is_expired(now=now):
            _logger.info("refresh_rejected", reason="expired", user_id=str(stored.user_id))
            raise AuthenticationError("The provided token is invalid or has expired.")

        user = await self._users.get_by_id(stored.user_id)
        if user is None:
            raise AuthenticationError("The provided token is invalid or has expired.")
        if not user.status.can_authenticate:
            raise AuthorizationError("This account is not permitted to sign in.")

        session = self._start_session(user, context=context)
        # The replacement row must exist before the old token can point at it,
        # since replaced_by_id is a foreign key onto the same table.
        await self._refresh_tokens.flush()
        stored.revoked_at = now
        stored.replaced_by_id = session.refresh_token.token_id
        await self._refresh_tokens.flush()

        _logger.info("refresh_succeeded", user_id=str(user.id))
        return session

    async def logout(self, *, refresh_token: str) -> None:
        """End the session identified by the given refresh token.

        Presenting an unknown or already-revoked token is not an error: the
        caller's intent — that this session should not work — already holds.

        Args:
            refresh_token: The encoded refresh JWT to invalidate.
        """
        claims = self._token_service.decode(refresh_token, expected_type=TokenType.REFRESH)
        stored = await self._refresh_tokens.get(claims.token_id)
        if stored is None:
            return
        await self._refresh_tokens.revoke(stored, at=datetime.now(UTC))
        _logger.info("logout", user_id=str(stored.user_id))

    async def logout_everywhere(self, *, user_id: uuid.UUID) -> int:
        """End every session belonging to an account.

        Args:
            user_id: Owner of the sessions.

        Returns:
            How many sessions were ended.
        """
        revoked = await self._refresh_tokens.revoke_all_for_user(user_id, at=datetime.now(UTC))
        _logger.info("logout_everywhere", user_id=str(user_id), sessions_revoked=revoked)
        return revoked

    @staticmethod
    def normalise_email(email: str) -> str:
        """Reduce an address to the canonical form stored in the database.

        Args:
            email: The address as supplied by the client.
        """
        return email.strip().lower()

    def _start_session(self, user: User, *, context: SessionContext) -> AuthenticatedSession:
        """Issue a token pair and persist the refresh side of it."""
        access = self._token_service.issue_access_token(user.id)
        refresh = self._token_service.issue_refresh_token(user.id)

        self._refresh_tokens.add(
            RefreshToken(
                id=refresh.token_id,
                user_id=user.id,
                expires_at=refresh.expires_at,
                user_agent=context.truncated_user_agent(),
                ip_address=context.ip_address,
            )
        )
        return AuthenticatedSession(
            user=user,
            access_token=access,
            refresh_token=refresh,
            access_token_ttl_seconds=self._settings.access_token_ttl_minutes * _SECONDS_PER_MINUTE,
        )

    def _assert_not_locked(self, user: User, *, now: datetime) -> None:
        """Reject sign-in while the account is inside its lockout window."""
        if user.locked_until is None or user.locked_until <= now:
            return
        retry_after = int((user.locked_until - now).total_seconds())
        _logger.info("login_blocked", reason="locked", user_id=str(user.id))
        raise AccountLockedError(
            "Too many failed sign-in attempts. Please try again later.",
            retry_after_seconds=max(retry_after, 1),
        )

    def _upgrade_password_hash_if_needed(self, user: User, password: str) -> None:
        """Re-hash the password when the stored hash uses outdated parameters.

        Runs only after a successful verification, so the plaintext is known to
        be correct and the account silently gains stronger protection.
        """
        if self._password_hasher.needs_rehash(user.password_hash):
            user.password_hash = self._password_hasher.hash(password)
            _logger.info("password_hash_upgraded", user_id=str(user.id))
