"""Integration tests for email verification.

The link is the only thing standing between an address and a verified account,
so these test what it refuses as carefully as what it accepts: a spent link, an
expired one, a guessed one, and a link belonging to somebody else.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from truvix.main import create_app
from truvix.modules.auth.dependencies import get_email_verification_service
from truvix.modules.auth.models import EmailVerificationToken
from truvix.modules.auth.verification import EmailVerificationService, hash_token
from truvix.modules.users.models import User
from truvix.shared.config import Settings
from truvix.shared.container import ApplicationContainer
from truvix.shared.dependencies import SessionDep
from truvix.shared.email import Email

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/register"
ME_URL = "/api/v1/auth/me"
SEND_URL = "/api/v1/auth/email/verification"
VERIFY_URL = "/api/v1/auth/email/verify"

_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_ACCEPTED = 202
_HTTP_UNAUTHORIZED = 401
_HTTP_CONFLICT = 409
_HTTP_UNPROCESSABLE = 422

_PASSWORD = "a-sufficiently-long-passphrase"


class RecordingSender:
    """Keeps every message instead of sending it."""

    def __init__(self) -> None:
        self.sent: list[Email] = []
        self.fails = False

    async def send(self, message: Email) -> bool:
        """Record the message."""
        if self.fails:
            return False
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

    # Only the transport is substituted; the tokens, their lifetime and every
    # rule about redeeming them are the real ones.
    def override(session: SessionDep) -> EmailVerificationService:
        return EmailVerificationService(session, sender, settings.email)

    app.dependency_overrides[get_email_verification_service] = override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


async def _expire(container: ApplicationContainer, token: str) -> None:
    """Age a link past its lifetime.

    Runs in its own transaction and commits. Holding the row open in the test's
    session instead would deadlock against the request that redeems it, which is
    the request under test.
    """
    async with container.database.transaction() as session:
        record = await session.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == hash_token(token)
            )
        )
        assert record is not None
        record.expires_at = datetime.now(UTC) - timedelta(minutes=1)


async def _register(client: AsyncClient, email: str) -> dict[str, str]:
    """Register an account and return its Authorization header."""
    response = await client.post(
        REGISTER_URL,
        json={"email": email, "password": _PASSWORD, "full_name": "Test Kullanici"},
    )
    assert response.status_code == _HTTP_CREATED, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


class TestSending:
    """A new account should be told how to verify itself."""

    async def test_registering_sends_a_link(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        await _register(client, "newcomer@truvix.app")

        assert len(sender.sent) == 1
        assert sender.sent[0].to == "newcomer@truvix.app"
        assert "token=" in sender.sent[0].body

    async def test_a_new_account_starts_unverified(self, client: AsyncClient) -> None:
        headers = await _register(client, "unverified@truvix.app")

        response = await client.get(ME_URL, headers=headers)

        assert response.json()["email_verified"] is False

    async def test_a_failing_mail_server_does_not_fail_the_registration(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        """The account exists; another link can be asked for later."""
        sender.fails = True

        response = await client.post(
            REGISTER_URL,
            json={
                "email": "mailserver-down@truvix.app",
                "password": _PASSWORD,
                "full_name": "Test",
            },
        )

        assert response.status_code == _HTTP_CREATED, response.text

    async def test_asking_again_sends_a_new_link(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        headers = await _register(client, "resend@truvix.app")
        first = sender.last_token

        response = await client.post(SEND_URL, headers=headers)

        assert response.status_code == _HTTP_ACCEPTED, response.text
        assert sender.last_token != first

    async def test_the_superseded_link_stops_working(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        """Two live links would mean a link could not be cancelled."""
        headers = await _register(client, "superseded@truvix.app")
        first = sender.last_token
        await client.post(SEND_URL, headers=headers)

        response = await client.post(VERIFY_URL, json={"token": first})

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_sending_requires_signing_in(self, client: AsyncClient) -> None:
        assert (await client.post(SEND_URL)).status_code == _HTTP_UNAUTHORIZED

    async def test_an_already_verified_address_is_refused(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        headers = await _register(client, "twice@truvix.app")
        await client.post(VERIFY_URL, json={"token": sender.last_token})

        response = await client.post(SEND_URL, headers=headers)

        assert response.status_code == _HTTP_CONFLICT


class TestVerifying:
    """What the link does, and what it refuses to do."""

    async def test_a_valid_link_verifies_the_address(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        headers = await _register(client, "verifies@truvix.app")

        response = await client.post(VERIFY_URL, json={"token": sender.last_token})

        assert response.status_code == _HTTP_OK, response.text
        assert response.json()["email_verified"] is True

        after = await client.get(ME_URL, headers=headers)
        assert after.json()["email_verified"] is True

    async def test_the_link_needs_no_session(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        """It arrives by mail and may be opened on a device with no session."""
        await _register(client, "otherdevice@truvix.app")

        response = await client.post(VERIFY_URL, json={"token": sender.last_token})

        assert response.status_code == _HTTP_OK

    async def test_a_link_can_only_be_used_once(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        await _register(client, "once@truvix.app")
        token = sender.last_token
        await client.post(VERIFY_URL, json={"token": token})

        response = await client.post(VERIFY_URL, json={"token": token})

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_a_guessed_link_is_refused(self, client: AsyncClient) -> None:
        response = await client.post(VERIFY_URL, json={"token": "n" * 43})

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_an_expired_link_is_refused(
        self,
        client: AsyncClient,
        sender: RecordingSender,
        container: ApplicationContainer,
    ) -> None:
        await _register(client, "expired@truvix.app")
        token = sender.last_token
        await _expire(container, token)

        response = await client.post(VERIFY_URL, json={"token": token})

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_an_unknown_and_an_expired_link_are_indistinguishable(
        self,
        client: AsyncClient,
        sender: RecordingSender,
        container: ApplicationContainer,
    ) -> None:
        """Otherwise the refusal itself reveals which tokens exist."""
        await _register(client, "indistinguishable@truvix.app")
        token = sender.last_token
        await _expire(container, token)

        expired = await client.post(VERIFY_URL, json={"token": token})
        unknown = await client.post(VERIFY_URL, json={"token": "z" * 43})

        assert expired.status_code == unknown.status_code
        assert expired.json()["detail"] == unknown.json()["detail"]

    async def test_one_accounts_link_does_not_verify_another(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        await _register(client, "owner@truvix.app")
        owners_token = sender.last_token
        headers = await _register(client, "bystander@truvix.app")

        await client.post(VERIFY_URL, json={"token": owners_token})

        bystander = await client.get(ME_URL, headers=headers)
        assert bystander.json()["email_verified"] is False


class TestTokenStorage:
    """What ends up in the database if it leaks."""

    async def test_the_token_is_not_stored_in_the_clear(
        self, client: AsyncClient, sender: RecordingSender, session: Any
    ) -> None:
        await _register(client, "hashed@truvix.app")
        token = sender.last_token

        stored = (await session.scalars(select(EmailVerificationToken))).all()
        digests = {record.token_hash for record in stored}

        assert token not in digests
        assert hash_token(token) in digests

    async def test_the_link_is_removed_once_spent(
        self, client: AsyncClient, sender: RecordingSender, session: Any
    ) -> None:
        await _register(client, "spent@truvix.app")
        token = sender.last_token

        await client.post(VERIFY_URL, json={"token": token})

        remaining = await session.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == hash_token(token)
            )
        )
        assert remaining is None

    async def test_deleting_an_account_takes_its_links_with_it(
        self, client: AsyncClient, sender: RecordingSender, session: Any
    ) -> None:
        """A token outliving its account would be a link to nothing."""
        await _register(client, "cascade@truvix.app")
        token = sender.last_token

        user = await session.scalar(select(User).where(User.email == "cascade@truvix.app"))
        assert user is not None
        await session.delete(user)
        await session.flush()

        remaining = await session.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == hash_token(token)
            )
        )
        assert remaining is None
