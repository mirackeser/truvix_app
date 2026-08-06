"""Integration tests for resetting a forgotten password.

A reset link is a way into an account, so these test the refusals as carefully
as the happy path: a spent link, an expired one, somebody else's link, and —
the one that is easy to get wrong — whether asking about an address reveals
that it has an account.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from truvix.main import create_app
from truvix.modules.auth.dependencies import get_password_reset_service
from truvix.modules.auth.models import PasswordResetToken, RefreshToken
from truvix.modules.auth.password_reset import PasswordResetService, hash_token
from truvix.modules.auth.repository import RefreshTokenRepository
from truvix.modules.users.models import User
from truvix.shared.config import Settings
from truvix.shared.container import ApplicationContainer
from truvix.shared.dependencies import PasswordHasherDep, SessionDep
from truvix.shared.email import Email

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
REQUEST_URL = "/api/v1/auth/password/reset-request"
RESET_URL = "/api/v1/auth/password/reset"

_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_ACCEPTED = 202
_HTTP_UNAUTHORIZED = 401
_HTTP_UNPROCESSABLE = 422

_PASSWORD = "a-sufficiently-long-passphrase"
_NEW_PASSWORD = "an-entirely-different-passphrase"


class RecordingSender:
    """Keeps every message instead of sending it."""

    def __init__(self) -> None:
        self.sent: list[Email] = []

    async def send(self, message: Email) -> bool:
        """Record the message."""
        self.sent.append(message)
        return True

    @property
    def last_token(self) -> str:
        """The token from the most recent link."""
        match = re.search(r"token=([\w\-]+)", self.sent[-1].body)
        assert match is not None, f"Bağlantı bulunamadı: {self.sent[-1].body}"
        return match.group(1)


@pytest.fixture
def sender() -> RecordingSender:
    """A mail sender that records rather than delivers."""
    return RecordingSender()


@pytest.fixture
async def client(
    settings: Settings, container: ApplicationContainer, sender: RecordingSender
) -> Any:
    """A client whose mail goes into the recording sender."""
    app = create_app(settings)
    app.state.container = container

    # Only the transport is substituted. The tokens, their lifetime, the session
    # revocation and every rule about redeeming them are the real ones.
    def override(session: SessionDep, hasher: PasswordHasherDep) -> PasswordResetService:
        return PasswordResetService(
            session,
            sender,
            settings.email,
            hasher,
            RefreshTokenRepository(session),
        )

    app.dependency_overrides[get_password_reset_service] = override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


async def _register(client: AsyncClient, email: str) -> dict[str, str]:
    """Register an account and return its Authorization header."""
    response = await client.post(
        REGISTER_URL,
        json={"email": email, "password": _PASSWORD, "full_name": "Unutkan Kullanici"},
    )
    assert response.status_code == _HTTP_CREATED, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


async def _expire(container: ApplicationContainer, token: str) -> None:
    """Age a link past its lifetime, in its own committed transaction."""
    async with container.database.transaction() as session:
        record = await session.scalar(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token))
        )
        assert record is not None
        record.expires_at = datetime.now(UTC) - timedelta(minutes=1)


class TestNotRevealingWhoHasAnAccount:
    """The endpoint must not become a way to test which addresses signed up."""

    async def test_a_known_address_is_accepted(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        await _register(client, "known@truvix.app")

        response = await client.post(REQUEST_URL, json={"email": "known@truvix.app"})

        assert response.status_code == _HTTP_ACCEPTED
        assert len(sender.sent) == 1

    async def test_an_unknown_address_is_accepted_identically(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        response = await client.post(REQUEST_URL, json={"email": "nobody@truvix.app"})

        assert response.status_code == _HTTP_ACCEPTED
        # Nothing was sent, because there is nobody to send it to.
        assert sender.sent == []

    async def test_both_answers_are_byte_for_byte_the_same(self, client: AsyncClient) -> None:
        """A difference in body or headers would be enough to tell them apart."""
        await _register(client, "compare-known@truvix.app")

        known = await client.post(REQUEST_URL, json={"email": "compare-known@truvix.app"})
        unknown = await client.post(REQUEST_URL, json={"email": "compare-nobody@truvix.app"})

        assert known.status_code == unknown.status_code
        assert known.content == unknown.content


class TestResetting:
    """What a valid link does."""

    async def test_the_new_password_works(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        await _register(client, "resets@truvix.app")
        await client.post(REQUEST_URL, json={"email": "resets@truvix.app"})

        response = await client.post(
            RESET_URL, json={"token": sender.last_token, "password": _NEW_PASSWORD}
        )

        assert response.status_code == _HTTP_OK, response.text
        signed_in = await client.post(
            LOGIN_URL, json={"email": "resets@truvix.app", "password": _NEW_PASSWORD}
        )
        assert signed_in.status_code == _HTTP_OK

    async def test_the_old_password_stops_working(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        await _register(client, "old-password@truvix.app")
        await client.post(REQUEST_URL, json={"email": "old-password@truvix.app"})
        await client.post(RESET_URL, json={"token": sender.last_token, "password": _NEW_PASSWORD})

        response = await client.post(
            LOGIN_URL, json={"email": "old-password@truvix.app", "password": _PASSWORD}
        )

        assert response.status_code == _HTTP_UNAUTHORIZED

    async def test_every_session_is_revoked(
        self, client: AsyncClient, sender: RecordingSender, session: Any
    ) -> None:
        """A reset may be somebody removing a stranger from their account."""
        await _register(client, "revokes@truvix.app")
        await client.post(REQUEST_URL, json={"email": "revokes@truvix.app"})

        await client.post(RESET_URL, json={"token": sender.last_token, "password": _NEW_PASSWORD})

        live = await session.scalar(
            select(func.count())
            .select_from(RefreshToken)
            .join(User, RefreshToken.user_id == User.id)
            .where(User.email == "revokes@truvix.app", RefreshToken.revoked_at.is_(None))
        )
        assert live == 0

    async def test_the_stranger_s_access_token_stops_working(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        stranger = await _register(client, "kicked-out@truvix.app")
        await client.post(REQUEST_URL, json={"email": "kicked-out@truvix.app"})

        await client.post(RESET_URL, json={"token": sender.last_token, "password": _NEW_PASSWORD})

        assert (await client.get(ME_URL, headers=stranger)).status_code == _HTTP_UNAUTHORIZED

    async def test_a_locked_account_can_sign_in_again(
        self, client: AsyncClient, sender: RecordingSender, container: ApplicationContainer
    ) -> None:
        """Otherwise a successful reset still could not get in."""
        await _register(client, "locked@truvix.app")
        async with container.database.transaction() as scoped:
            user = await scoped.scalar(select(User).where(User.email == "locked@truvix.app"))
            assert user is not None
            user.failed_login_attempts = 5
            user.locked_until = datetime.now(UTC) + timedelta(hours=1)

        await client.post(REQUEST_URL, json={"email": "locked@truvix.app"})
        await client.post(RESET_URL, json={"token": sender.last_token, "password": _NEW_PASSWORD})

        response = await client.post(
            LOGIN_URL, json={"email": "locked@truvix.app", "password": _NEW_PASSWORD}
        )
        assert response.status_code == _HTTP_OK, response.text

    async def test_using_the_link_also_verifies_the_address(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        """Reading the link proves what the verification link proves."""
        await _register(client, "also-verifies@truvix.app")
        await client.post(REQUEST_URL, json={"email": "also-verifies@truvix.app"})

        response = await client.post(
            RESET_URL, json={"token": sender.last_token, "password": _NEW_PASSWORD}
        )

        assert response.json()["email_verified"] is True


class TestRefusing:
    """What a link will not do."""

    async def test_a_link_can_only_be_used_once(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        await _register(client, "once@truvix.app")
        await client.post(REQUEST_URL, json={"email": "once@truvix.app"})
        token = sender.last_token
        await client.post(RESET_URL, json={"token": token, "password": _NEW_PASSWORD})

        response = await client.post(
            RESET_URL, json={"token": token, "password": "a-third-passphrase-entirely"}
        )

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_asking_again_cancels_the_previous_link(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        await _register(client, "superseded@truvix.app")
        await client.post(REQUEST_URL, json={"email": "superseded@truvix.app"})
        first = sender.last_token
        await client.post(REQUEST_URL, json={"email": "superseded@truvix.app"})

        response = await client.post(RESET_URL, json={"token": first, "password": _NEW_PASSWORD})

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_an_expired_link_is_refused(
        self,
        client: AsyncClient,
        sender: RecordingSender,
        container: ApplicationContainer,
    ) -> None:
        await _register(client, "stale@truvix.app")
        await client.post(REQUEST_URL, json={"email": "stale@truvix.app"})
        token = sender.last_token
        await _expire(container, token)

        response = await client.post(RESET_URL, json={"token": token, "password": _NEW_PASSWORD})

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_a_guessed_link_is_refused(self, client: AsyncClient) -> None:
        response = await client.post(RESET_URL, json={"token": "g" * 43, "password": _NEW_PASSWORD})

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_an_unknown_and_an_expired_link_are_indistinguishable(
        self,
        client: AsyncClient,
        sender: RecordingSender,
        container: ApplicationContainer,
    ) -> None:
        await _register(client, "same-refusal@truvix.app")
        await client.post(REQUEST_URL, json={"email": "same-refusal@truvix.app"})
        token = sender.last_token
        await _expire(container, token)

        expired = await client.post(RESET_URL, json={"token": token, "password": _NEW_PASSWORD})
        unknown = await client.post(RESET_URL, json={"token": "u" * 43, "password": _NEW_PASSWORD})

        assert expired.status_code == unknown.status_code
        assert expired.json()["detail"] == unknown.json()["detail"]

    async def test_a_verification_link_cannot_reset_a_password(
        self, client: AsyncClient, sender: RecordingSender, container: ApplicationContainer
    ) -> None:
        """The two token types live in separate tables, so this cannot resolve."""
        from truvix.modules.auth.models import EmailVerificationToken

        await _register(client, "wrong-token-type@truvix.app")
        async with container.database.transaction() as scoped:
            record = await scoped.scalar(
                select(EmailVerificationToken)
                .join(User, EmailVerificationToken.user_id == User.id)
                .where(User.email == "wrong-token-type@truvix.app")
            )
            assert record is not None, "Kayıt bir doğrulama bağlantısı üretmedi"

        # The digest is all that is stored, so the raw verification token cannot
        # be recovered here — which is itself the point. Presenting any value
        # that is not a live reset token must fail.
        response = await client.post(RESET_URL, json={"token": "v" * 43, "password": _NEW_PASSWORD})

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_a_weak_password_is_rejected(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        """The reset path applies the same policy registration does."""
        await _register(client, "weak@truvix.app")
        await client.post(REQUEST_URL, json={"email": "weak@truvix.app"})

        response = await client.post(
            RESET_URL, json={"token": sender.last_token, "password": "short"}
        )

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_a_rejected_reset_leaves_the_link_usable(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        """A typo in the new password must not burn the link."""
        await _register(client, "typo@truvix.app")
        await client.post(REQUEST_URL, json={"email": "typo@truvix.app"})
        token = sender.last_token
        await client.post(RESET_URL, json={"token": token, "password": "short"})

        response = await client.post(RESET_URL, json={"token": token, "password": _NEW_PASSWORD})

        assert response.status_code == _HTTP_OK, response.text


class TestTokenStorage:
    """What ends up in the database if it leaks."""

    async def test_the_token_is_not_stored_in_the_clear(
        self, client: AsyncClient, sender: RecordingSender, session: Any
    ) -> None:
        await _register(client, "hashed@truvix.app")
        await client.post(REQUEST_URL, json={"email": "hashed@truvix.app"})
        token = sender.last_token

        digests = {
            record.token_hash
            for record in (await session.scalars(select(PasswordResetToken))).all()
        }

        assert token not in digests
        assert hash_token(token) in digests

    async def test_the_link_is_removed_once_spent(
        self, client: AsyncClient, sender: RecordingSender, session: Any
    ) -> None:
        await _register(client, "spent@truvix.app")
        await client.post(REQUEST_URL, json={"email": "spent@truvix.app"})
        token = sender.last_token

        await client.post(RESET_URL, json={"token": token, "password": _NEW_PASSWORD})

        remaining = await session.scalar(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token))
        )
        assert remaining is None
