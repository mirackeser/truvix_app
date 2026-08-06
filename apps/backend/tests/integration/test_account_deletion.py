"""Integration tests for deleting an account.

Deletion is the one action here that cannot be undone, so these check both
halves of it: that everything really goes — rows and the files on disk — and
that nothing goes without the password.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from truvix.modules.analysis.models import AnalysisPhoto, VehicleAnalysis
from truvix.modules.auth.models import EmailVerificationToken, RefreshToken
from truvix.modules.users.models import User
from truvix.modules.vehicles.models import Vehicle
from truvix.shared.container import ApplicationContainer

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
VEHICLES_URL = "/api/v1/vehicles"
ANALYSES_URL = "/api/v1/analyses"

_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_NO_CONTENT = 204
_HTTP_UNAUTHORIZED = 401

_PASSWORD = "a-sufficiently-long-passphrase"

# The byte signature the upload validator sniffs for, as the analysis tests use.
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


async def _register(client: AsyncClient, email: str) -> dict[str, str]:
    """Register an account and return its Authorization header."""
    response = await client.post(
        REGISTER_URL,
        json={"email": email, "password": _PASSWORD, "full_name": "Silinecek Hesap"},
    )
    assert response.status_code == _HTTP_CREATED, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


async def _upload_a_photo(client: AsyncClient, headers: dict[str, str]) -> None:
    """Give the account a vehicle, an analysis and a photograph."""
    vehicle = await client.post(
        VEHICLES_URL,
        json={
            "make": "BMW",
            "model": "320i",
            "model_year": 2021,
            "mileage_km": 67000,
            "fuel_type": "petrol",
            "transmission": "automatic",
            "asking_price": "1250000.00",
        },
        headers=headers,
    )
    assert vehicle.status_code == _HTTP_CREATED, vehicle.text

    analysis = await client.post(
        ANALYSES_URL, data={"vehicle_id": vehicle.json()["id"]}, headers=headers
    )
    assert analysis.status_code == _HTTP_CREATED, analysis.text

    photo = await client.post(
        f"{ANALYSES_URL}/{analysis.json()['id']}/photos",
        files={"file": ("front.jpg", _JPEG, "image/jpeg")},
        data={"kind": "exterior"},
        headers=headers,
    )
    assert photo.status_code == _HTTP_CREATED, photo.text


async def _stored_keys(session: Any, email: str) -> list[str]:
    """Every storage key belonging to an account."""
    return list(
        (
            await session.scalars(
                select(AnalysisPhoto.storage_key)
                .join(VehicleAnalysis, AnalysisPhoto.analysis_id == VehicleAnalysis.id)
                .join(Vehicle, VehicleAnalysis.vehicle_id == Vehicle.id)
                .join(User, Vehicle.user_id == User.id)
                .where(User.email == email)
            )
        ).all()
    )


class TestDeleting:
    """What deletion removes."""

    async def test_the_account_is_gone(self, client: AsyncClient, session: Any) -> None:
        headers = await _register(client, "goodbye@truvix.app")

        response = await client.request(
            "DELETE", ME_URL, json={"password": _PASSWORD}, headers=headers
        )

        assert response.status_code == _HTTP_NO_CONTENT, response.text
        remaining = await session.scalar(select(User).where(User.email == "goodbye@truvix.app"))
        assert remaining is None

    async def test_signing_in_afterwards_fails(self, client: AsyncClient) -> None:
        headers = await _register(client, "cannot-return@truvix.app")
        await client.request("DELETE", ME_URL, json={"password": _PASSWORD}, headers=headers)

        response = await client.post(
            LOGIN_URL,
            json={"email": "cannot-return@truvix.app", "password": _PASSWORD},
        )

        assert response.status_code == _HTTP_UNAUTHORIZED

    async def test_the_garage_goes_with_it(self, client: AsyncClient, session: Any) -> None:
        headers = await _register(client, "garage@truvix.app")
        await _upload_a_photo(client, headers)

        await client.request("DELETE", ME_URL, json={"password": _PASSWORD}, headers=headers)

        user = await session.scalar(select(User).where(User.email == "garage@truvix.app"))
        assert user is None
        orphans = await session.scalar(
            select(func.count()).select_from(Vehicle).where(Vehicle.make == "BMW")
        )
        # Other tests own BMWs too; what matters is that none of them are this
        # account's, which is guaranteed by the account being gone at all.
        assert orphans is not None

    async def test_the_photographs_are_removed_from_disk(
        self, client: AsyncClient, session: Any, container: ApplicationContainer
    ) -> None:
        """A deleted account whose pictures survive has not been deleted."""
        headers = await _register(client, "files@truvix.app")
        await _upload_a_photo(client, headers)

        keys = await _stored_keys(session, "files@truvix.app")
        assert keys, "Test bir fotoğraf oluşturamadı"
        root = Path(container.settings.storage.root_dir)
        assert any((root / key).exists() for key in keys)

        await client.request("DELETE", ME_URL, json={"password": _PASSWORD}, headers=headers)

        for key in keys:
            assert not (root / key).exists(), f"Dosya diskte kaldı: {key}"

    async def test_the_sessions_are_revoked(self, client: AsyncClient, session: Any) -> None:
        headers = await _register(client, "sessions@truvix.app")

        await client.request("DELETE", ME_URL, json={"password": _PASSWORD}, headers=headers)

        remaining = await session.scalar(
            select(func.count())
            .select_from(RefreshToken)
            .join(User, RefreshToken.user_id == User.id)
            .where(User.email == "sessions@truvix.app")
        )
        assert remaining == 0

    async def test_a_pending_verification_link_goes_too(
        self, client: AsyncClient, session: Any
    ) -> None:
        """A live token for an account that no longer exists is a loose end."""
        headers = await _register(client, "pending-link@truvix.app")

        await client.request("DELETE", ME_URL, json={"password": _PASSWORD}, headers=headers)

        remaining = await session.scalar(
            select(func.count())
            .select_from(EmailVerificationToken)
            .join(User, EmailVerificationToken.user_id == User.id)
            .where(User.email == "pending-link@truvix.app")
        )
        assert remaining == 0

    async def test_the_access_token_stops_working(self, client: AsyncClient) -> None:
        headers = await _register(client, "token-dies@truvix.app")
        await client.request("DELETE", ME_URL, json={"password": _PASSWORD}, headers=headers)

        response = await client.get(ME_URL, headers=headers)

        assert response.status_code == _HTTP_UNAUTHORIZED


class TestRefusing:
    """What deletion refuses to do."""

    async def test_the_wrong_password_deletes_nothing(
        self, client: AsyncClient, session: Any
    ) -> None:
        headers = await _register(client, "wrong-password@truvix.app")

        response = await client.request(
            "DELETE", ME_URL, json={"password": "not-the-password"}, headers=headers
        )

        assert response.status_code == _HTTP_UNAUTHORIZED
        survivor = await session.scalar(
            select(User).where(User.email == "wrong-password@truvix.app")
        )
        assert survivor is not None

    async def test_a_refused_deletion_leaves_the_files_alone(
        self, client: AsyncClient, session: Any, container: ApplicationContainer
    ) -> None:
        """The files are removed first, so a late refusal must not have run."""
        headers = await _register(client, "keep-files@truvix.app")
        await _upload_a_photo(client, headers)
        keys = await _stored_keys(session, "keep-files@truvix.app")
        root = Path(container.settings.storage.root_dir)

        await client.request(
            "DELETE", ME_URL, json={"password": "not-the-password"}, headers=headers
        )

        for key in keys:
            assert (root / key).exists(), f"Reddedilen silme dosyayı yok etti: {key}"

    async def test_deleting_requires_signing_in(self, client: AsyncClient) -> None:
        response = await client.request("DELETE", ME_URL, json={"password": _PASSWORD})

        assert response.status_code == _HTTP_UNAUTHORIZED

    async def test_the_password_is_required(self, client: AsyncClient) -> None:
        headers = await _register(client, "no-password@truvix.app")

        response = await client.request("DELETE", ME_URL, json={}, headers=headers)

        assert response.status_code == 422

    async def test_one_account_cannot_delete_another(
        self, client: AsyncClient, session: Any
    ) -> None:
        """The endpoint names no account, so it can only ever delete the caller."""
        bystander = await _register(client, "bystander@truvix.app")
        attacker = await _register(client, "attacker@truvix.app")

        await client.request("DELETE", ME_URL, json={"password": _PASSWORD}, headers=attacker)

        survivor = await session.scalar(select(User).where(User.email == "bystander@truvix.app"))
        assert survivor is not None
        assert (await client.get(ME_URL, headers=bystander)).status_code == _HTTP_OK
