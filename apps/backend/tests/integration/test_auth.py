"""Integration tests for registration, sign-in and session rotation."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from truvix.modules.auth.models import RefreshToken
from truvix.modules.users.models import SubscriptionTier, User, UserStatus
from truvix.shared.container import ApplicationContainer

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
LOGOUT_ALL_URL = "/api/v1/auth/logout-all"
ME_URL = "/api/v1/auth/me"

_EMAIL = "kerem@truvix.app"
_PASSWORD = "a-sufficiently-long-passphrase"
_FULL_NAME = "Kerem Yilmaz"

_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_NO_CONTENT = 204
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_CONFLICT = 409
_HTTP_UNPROCESSABLE = 422


def _registration_payload(**overrides: Any) -> dict[str, Any]:
    """Build a valid registration payload with optional overrides."""
    payload: dict[str, Any] = {
        "email": _EMAIL,
        "password": _PASSWORD,
        "full_name": _FULL_NAME,
    }
    payload.update(overrides)
    return payload


async def _register(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    """Register an account and return the decoded response body."""
    response = await client.post(REGISTER_URL, json=_registration_payload(**overrides))
    assert response.status_code == _HTTP_CREATED, response.text
    body: dict[str, Any] = response.json()
    return body


class TestRegistration:
    async def test_creates_an_account_and_issues_tokens(self, client: AsyncClient) -> None:
        body = await _register(client)

        assert body["user"]["email"] == _EMAIL
        assert body["user"]["full_name"] == _FULL_NAME
        assert body["user"]["subscription_tier"] == SubscriptionTier.FREE.value
        assert body["user"]["email_verified"] is False
        assert body["tokens"]["token_type"] == "bearer"
        assert body["tokens"]["access_token"]
        assert body["tokens"]["refresh_token"]
        assert body["tokens"]["expires_in"] > 0

    async def test_never_returns_the_password_hash(self, client: AsyncClient) -> None:
        body = await _register(client)

        assert "password" not in str(body)
        assert "password_hash" not in body["user"]

    async def test_email_is_stored_normalised(
        self, client: AsyncClient, container: ApplicationContainer
    ) -> None:
        await _register(client, email="Kerem@Truvix.APP")

        async with container.database.transaction() as session:
            stored = await session.scalar(select(User))

        assert stored is not None
        assert stored.email == "kerem@truvix.app"

    async def test_duplicate_email_is_rejected(self, client: AsyncClient) -> None:
        await _register(client)

        response = await client.post(REGISTER_URL, json=_registration_payload())

        assert response.status_code == _HTTP_CONFLICT
        assert response.json()["code"] == "conflict"

    async def test_duplicate_email_in_different_casing_is_rejected(
        self, client: AsyncClient
    ) -> None:
        await _register(client)

        response = await client.post(
            REGISTER_URL, json=_registration_payload(email="KEREM@TRUVIX.APP")
        )

        assert response.status_code == _HTTP_CONFLICT

    @pytest.mark.parametrize(
        "overrides",
        [
            {"password": "short"},
            {"email": "not-an-email"},
            {"full_name": "K"},
            {"phone_number": "05551234567"},
            {"password": "   " * 5},
        ],
        ids=["short_password", "bad_email", "short_name", "non_e164_phone", "blank_password"],
    )
    async def test_invalid_payloads_are_rejected(
        self, client: AsyncClient, overrides: dict[str, Any]
    ) -> None:
        response = await client.post(REGISTER_URL, json=_registration_payload(**overrides))

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_password_containing_the_email_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post(
            REGISTER_URL,
            json=_registration_payload(email="kerem@truvix.app", password="kerem-is-my-password"),
        )

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_accepts_a_valid_e164_phone_number(self, client: AsyncClient) -> None:
        body = await _register(client, phone_number="+905551234567")

        assert body["user"]["phone_number"] == "+905551234567"


class TestLogin:
    async def test_valid_credentials_return_a_new_token_pair(self, client: AsyncClient) -> None:
        registration = await _register(client)

        response = await client.post(LOGIN_URL, json={"email": _EMAIL, "password": _PASSWORD})

        assert response.status_code == _HTTP_OK
        body = response.json()
        assert body["user"]["id"] == registration["user"]["id"]
        assert body["tokens"]["refresh_token"] != registration["tokens"]["refresh_token"]

    async def test_login_is_case_insensitive_on_email(self, client: AsyncClient) -> None:
        await _register(client)

        response = await client.post(
            LOGIN_URL, json={"email": "KEREM@TRUVIX.APP", "password": _PASSWORD}
        )

        assert response.status_code == _HTTP_OK

    async def test_wrong_password_is_rejected(self, client: AsyncClient) -> None:
        await _register(client)

        response = await client.post(
            LOGIN_URL, json={"email": _EMAIL, "password": "wrong-password"}
        )

        assert response.status_code == _HTTP_UNAUTHORIZED
        assert response.json()["code"] == "authentication_failed"

    async def test_unknown_email_gives_the_same_error_as_a_wrong_password(
        self, client: AsyncClient
    ) -> None:
        await _register(client)

        unknown = await client.post(
            LOGIN_URL, json={"email": "nobody@truvix.app", "password": _PASSWORD}
        )
        wrong = await client.post(LOGIN_URL, json={"email": _EMAIL, "password": "wrong-password"})

        assert unknown.status_code == wrong.status_code
        assert unknown.json()["detail"] == wrong.json()["detail"]

    async def test_successful_login_records_the_timestamp(
        self, client: AsyncClient, container: ApplicationContainer
    ) -> None:
        await _register(client)
        await client.post(LOGIN_URL, json={"email": _EMAIL, "password": _PASSWORD})

        async with container.database.transaction() as session:
            stored = await session.scalar(select(User))

        assert stored is not None
        assert stored.last_login_at is not None


class TestAccountLockout:
    async def test_repeated_failures_lock_the_account(
        self, client: AsyncClient, container: ApplicationContainer
    ) -> None:
        await _register(client)
        attempts = container.settings.security.max_failed_login_attempts

        for _ in range(attempts):
            await client.post(LOGIN_URL, json={"email": _EMAIL, "password": "wrong-password"})

        response = await client.post(LOGIN_URL, json={"email": _EMAIL, "password": _PASSWORD})

        assert response.status_code == _HTTP_UNAUTHORIZED
        assert response.json()["code"] == "account_locked"
        assert int(response.headers["retry-after"]) > 0

    async def test_a_successful_login_resets_the_failure_count(
        self, client: AsyncClient, container: ApplicationContainer
    ) -> None:
        await _register(client)
        attempts = container.settings.security.max_failed_login_attempts

        for _ in range(attempts - 1):
            await client.post(LOGIN_URL, json={"email": _EMAIL, "password": "wrong-password"})
        await client.post(LOGIN_URL, json={"email": _EMAIL, "password": _PASSWORD})

        async with container.database.transaction() as session:
            stored = await session.scalar(select(User))

        assert stored is not None
        assert stored.failed_login_attempts == 0
        assert stored.locked_until is None


class TestSuspendedAccounts:
    async def test_a_suspended_account_cannot_sign_in(
        self, client: AsyncClient, container: ApplicationContainer
    ) -> None:
        await _register(client)

        async with container.database.transaction() as session:
            user = await session.scalar(select(User))
            assert user is not None
            user.status = UserStatus.SUSPENDED

        response = await client.post(LOGIN_URL, json={"email": _EMAIL, "password": _PASSWORD})

        assert response.status_code == _HTTP_FORBIDDEN
        assert response.json()["code"] == "permission_denied"


class TestRefreshRotation:
    async def test_refresh_returns_a_different_pair(self, client: AsyncClient) -> None:
        registration = await _register(client)
        original = registration["tokens"]["refresh_token"]

        response = await client.post(REFRESH_URL, json={"refresh_token": original})

        assert response.status_code == _HTTP_OK
        assert response.json()["tokens"]["refresh_token"] != original

    async def test_the_rotated_token_is_recorded_as_replaced(
        self, client: AsyncClient, container: ApplicationContainer
    ) -> None:
        registration = await _register(client)
        original = registration["tokens"]["refresh_token"]

        await client.post(REFRESH_URL, json={"refresh_token": original})

        async with container.database.transaction() as session:
            tokens = (await session.scalars(select(RefreshToken))).all()

        rotated = [token for token in tokens if token.revoked_at is not None]
        assert len(rotated) == 1
        assert rotated[0].replaced_by_id is not None

    async def test_replaying_a_rotated_token_is_rejected(self, client: AsyncClient) -> None:
        registration = await _register(client)
        original = registration["tokens"]["refresh_token"]
        await client.post(REFRESH_URL, json={"refresh_token": original})

        replay = await client.post(REFRESH_URL, json={"refresh_token": original})

        assert replay.status_code == _HTTP_UNAUTHORIZED

    async def test_replay_revokes_every_session_for_the_account(
        self, client: AsyncClient, container: ApplicationContainer
    ) -> None:
        registration = await _register(client)
        original = registration["tokens"]["refresh_token"]
        rotated = await client.post(REFRESH_URL, json={"refresh_token": original})
        current = rotated.json()["tokens"]["refresh_token"]

        await client.post(REFRESH_URL, json={"refresh_token": original})

        # The legitimate holder's token must also stop working, because a replay
        # means the credential is known to someone else.
        follow_up = await client.post(REFRESH_URL, json={"refresh_token": current})
        assert follow_up.status_code == _HTTP_UNAUTHORIZED

        async with container.database.transaction() as session:
            tokens = (await session.scalars(select(RefreshToken))).all()
        assert all(token.revoked_at is not None for token in tokens)

    async def test_an_access_token_cannot_be_used_to_refresh(self, client: AsyncClient) -> None:
        registration = await _register(client)

        response = await client.post(
            REFRESH_URL, json={"refresh_token": registration["tokens"]["access_token"]}
        )

        assert response.status_code == _HTTP_UNAUTHORIZED

    async def test_a_malformed_token_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post(REFRESH_URL, json={"refresh_token": "not.a.jwt"})

        assert response.status_code == _HTTP_UNAUTHORIZED


class TestCurrentUser:
    async def test_returns_the_authenticated_account(self, client: AsyncClient) -> None:
        registration = await _register(client)
        access = registration["tokens"]["access_token"]

        response = await client.get(ME_URL, headers={"Authorization": f"Bearer {access}"})

        assert response.status_code == _HTTP_OK
        assert response.json()["email"] == _EMAIL

    async def test_a_missing_header_is_rejected(self, client: AsyncClient) -> None:
        response = await client.get(ME_URL)

        assert response.status_code == _HTTP_UNAUTHORIZED
        assert response.json()["code"] == "authentication_failed"

    async def test_a_refresh_token_is_not_accepted_as_a_bearer_token(
        self, client: AsyncClient
    ) -> None:
        registration = await _register(client)
        refresh_token = registration["tokens"]["refresh_token"]

        response = await client.get(ME_URL, headers={"Authorization": f"Bearer {refresh_token}"})

        assert response.status_code == _HTTP_UNAUTHORIZED

    async def test_a_garbage_token_is_rejected(self, client: AsyncClient) -> None:
        response = await client.get(ME_URL, headers={"Authorization": "Bearer nonsense"})

        assert response.status_code == _HTTP_UNAUTHORIZED


class TestLogout:
    async def test_the_session_stops_working(self, client: AsyncClient) -> None:
        registration = await _register(client)
        refresh_token = registration["tokens"]["refresh_token"]

        logout = await client.post(LOGOUT_URL, json={"refresh_token": refresh_token})

        assert logout.status_code == _HTTP_NO_CONTENT
        replay = await client.post(REFRESH_URL, json={"refresh_token": refresh_token})
        assert replay.status_code == _HTTP_UNAUTHORIZED

    async def test_logging_out_twice_is_not_an_error(self, client: AsyncClient) -> None:
        registration = await _register(client)
        refresh_token = registration["tokens"]["refresh_token"]

        await client.post(LOGOUT_URL, json={"refresh_token": refresh_token})
        second = await client.post(LOGOUT_URL, json={"refresh_token": refresh_token})

        assert second.status_code == _HTTP_NO_CONTENT

    async def test_logout_all_ends_every_session(self, client: AsyncClient) -> None:
        registration = await _register(client)
        access = registration["tokens"]["access_token"]
        second_login = await client.post(LOGIN_URL, json={"email": _EMAIL, "password": _PASSWORD})
        other_refresh = second_login.json()["tokens"]["refresh_token"]

        response = await client.post(LOGOUT_ALL_URL, headers={"Authorization": f"Bearer {access}"})

        assert response.status_code == _HTTP_NO_CONTENT
        first = await client.post(
            REFRESH_URL, json={"refresh_token": registration["tokens"]["refresh_token"]}
        )
        second = await client.post(REFRESH_URL, json={"refresh_token": other_refresh})
        assert first.status_code == _HTTP_UNAUTHORIZED
        assert second.status_code == _HTTP_UNAUTHORIZED

    async def test_logout_all_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(LOGOUT_ALL_URL)

        assert response.status_code == _HTTP_UNAUTHORIZED
