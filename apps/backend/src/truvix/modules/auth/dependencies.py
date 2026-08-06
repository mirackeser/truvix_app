"""Dependency providers for authentication and the current caller."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from truvix.modules.auth.journal import SecurityJournal
from truvix.modules.auth.password_reset import PasswordResetService
from truvix.modules.auth.repository import RefreshTokenRepository
from truvix.modules.auth.service import AuthService, SessionContext
from truvix.modules.auth.verification import EmailVerificationService
from truvix.modules.users.deletion import AccountDeletionService
from truvix.modules.users.models import User
from truvix.modules.users.repository import UserRepository
from truvix.shared.dependencies import (
    ContainerDep,
    PasswordHasherDep,
    SessionDep,
    SettingsDep,
    TokenServiceDep,
)
from truvix.shared.email import build_email_sender
from truvix.shared.errors import AuthenticationError, AuthorizationError
from truvix.shared.ratelimit import client_identifier
from truvix.shared.security import TokenType

# auto_error is disabled so a missing header raises our own problem document
# rather than FastAPI's default, keeping every error response shaped alike.
_bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")

BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)]


def get_user_repository(session: SessionDep) -> UserRepository:
    """Provide the user repository bound to the request's transaction."""
    return UserRepository(session)


def get_refresh_token_repository(session: SessionDep) -> RefreshTokenRepository:
    """Provide the refresh token repository bound to the request's transaction."""
    return RefreshTokenRepository(session)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
RefreshTokenRepositoryDep = Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)]


def get_security_journal(container: ContainerDep) -> SecurityJournal:
    """Provide the journal, which writes outside the request transaction."""
    return SecurityJournal(container.database)


SecurityJournalDep = Annotated[SecurityJournal, Depends(get_security_journal)]


def get_auth_service(
    users: UserRepositoryDep,
    refresh_tokens: RefreshTokenRepositoryDep,
    password_hasher: PasswordHasherDep,
    token_service: TokenServiceDep,
    settings: SettingsDep,
    journal: SecurityJournalDep,
) -> AuthService:
    """Provide the authentication service for the current request."""
    return AuthService(
        users=users,
        refresh_tokens=refresh_tokens,
        password_hasher=password_hasher,
        token_service=token_service,
        settings=settings.security,
        journal=journal,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_email_verification_service(
    session: SessionDep, settings: SettingsDep
) -> EmailVerificationService:
    """Provide the email verification service for the current request."""
    return EmailVerificationService(
        session,
        build_email_sender(settings.email),
        settings.email,
    )


EmailVerificationServiceDep = Annotated[
    EmailVerificationService, Depends(get_email_verification_service)
]


def get_password_reset_service(
    session: SessionDep,
    settings: SettingsDep,
    hasher: PasswordHasherDep,
    tokens: RefreshTokenRepositoryDep,
) -> PasswordResetService:
    """Provide the password reset service for the current request."""
    return PasswordResetService(
        session,
        build_email_sender(settings.email),
        settings.email,
        hasher,
        tokens,
    )


PasswordResetServiceDep = Annotated[PasswordResetService, Depends(get_password_reset_service)]


def get_account_deletion_service(
    session: SessionDep, container: ContainerDep, hasher: PasswordHasherDep
) -> AccountDeletionService:
    """Provide the account deletion service for the current request."""
    return AccountDeletionService(session, container.file_storage, hasher)


AccountDeletionServiceDep = Annotated[AccountDeletionService, Depends(get_account_deletion_service)]


def get_session_context(request: Request) -> SessionContext:
    """Capture the calling client's details for session bookkeeping."""
    identifier = client_identifier(request)
    return SessionContext(
        user_agent=request.headers.get("User-Agent"),
        ip_address=identifier if identifier != "unknown" else None,
    )


SessionContextDep = Annotated[SessionContext, Depends(get_session_context)]


async def get_current_user(
    credentials: BearerCredentials,
    token_service: TokenServiceDep,
    users: UserRepositoryDep,
) -> User:
    """Resolve the account behind the request's bearer token.

    Returns:
        The authenticated account.

    Raises:
        AuthenticationError: If the header is missing, or the token is invalid,
            expired or refers to an account that no longer exists.
        AuthorizationError: If the account may no longer authenticate.
    """
    if credentials is None:
        raise AuthenticationError("An access token is required for this endpoint.")

    claims = token_service.decode(credentials.credentials, expected_type=TokenType.ACCESS)

    user = await users.get_by_id(claims.subject)
    if user is None:
        raise AuthenticationError("The provided token is invalid or has expired.")
    if not user.status.can_authenticate:
        raise AuthorizationError("This account is not permitted to access the API.")

    # A password reset invalidates tokens issued before it, so an access token
    # already in a stranger's hands stops working at once rather than lasting
    # out its half hour. The `iat` claim has second precision, so a token minted
    # in the same second as the reset survives; a one-second window is not worth
    # the risk of rejecting the legitimate sign-in that follows.
    if user.tokens_invalid_before is not None and claims.issued_at < user.tokens_invalid_before:
        raise AuthenticationError("The provided token is invalid or has expired.")

    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
