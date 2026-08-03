"""Integration tests for the analysis workflow."""

from __future__ import annotations

import io
from typing import Any

import pytest
from httpx import AsyncClient

from truvix.shared.container import ApplicationContainer

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/register"
VEHICLES_URL = "/api/v1/vehicles"
ANALYSES_URL = "/api/v1/analyses"

_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_UNAUTHORIZED = 401
_HTTP_NOT_FOUND = 404
_HTTP_CONFLICT = 409
_HTTP_UNPROCESSABLE = 422

_PASSWORD = "a-sufficiently-long-passphrase"

# Minimal but genuine file signatures.
_JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
_PDF_BYTES = b"%PDF-1.7\n%%EOF\n"
_EXE_BYTES = b"MZ\x90\x00" + b"\x00" * 64


async def _sign_up(client: AsyncClient, email: str) -> dict[str, str]:
    """Register an account and return its Authorization header."""
    response = await client.post(
        REGISTER_URL,
        json={"email": email, "password": _PASSWORD, "full_name": "Test Kullanici"},
    )
    assert response.status_code == _HTTP_CREATED, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


async def _save_vehicle(client: AsyncClient, headers: dict[str, str], **overrides: Any) -> str:
    """Save a vehicle and return its id."""
    payload: dict[str, Any] = {
        "make": "BMW",
        "model": "320i",
        "model_year": 2021,
        "mileage_km": 67000,
        "fuel_type": "petrol",
        "transmission": "automatic",
        "asking_price": "1250000.00",
    }
    payload.update(overrides)
    response = await client.post(VEHICLES_URL, json=payload, headers=headers)
    assert response.status_code == _HTTP_CREATED, response.text
    vehicle_id: str = response.json()["id"]
    return vehicle_id


async def _open_analysis(client: AsyncClient, headers: dict[str, str], vehicle_id: str) -> str:
    """Create a pending analysis and return its id."""
    response = await client.post(ANALYSES_URL, data={"vehicle_id": vehicle_id}, headers=headers)
    assert response.status_code == _HTTP_CREATED, response.text
    analysis_id: str = response.json()["id"]
    return analysis_id


def _upload(name: str, payload: bytes, declared_type: str = "image/jpeg") -> dict[str, Any]:
    """Build the files argument for an upload request."""
    return {"file": (name, io.BytesIO(payload), declared_type)}


@pytest.fixture
async def owner(client: AsyncClient) -> dict[str, str]:
    return await _sign_up(client, "owner@truvix.app")


@pytest.fixture
async def intruder(client: AsyncClient) -> dict[str, str]:
    return await _sign_up(client, "intruder@truvix.app")


class TestCreatingAnalyses:
    async def test_opens_in_pending_state(self, client: AsyncClient, owner: dict[str, str]) -> None:
        vehicle_id = await _save_vehicle(client, owner)

        response = await client.post(ANALYSES_URL, data={"vehicle_id": vehicle_id}, headers=owner)

        body = response.json()
        assert body["status"] == "pending"
        assert body["trust_score"] is None
        assert body["findings"] == []

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(ANALYSES_URL, data={"vehicle_id": str(0)})

        assert response.status_code in {_HTTP_UNAUTHORIZED, _HTTP_UNPROCESSABLE}

    async def test_cannot_target_another_accounts_vehicle(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)

        response = await client.post(
            ANALYSES_URL, data={"vehicle_id": vehicle_id}, headers=intruder
        )

        assert response.status_code == _HTTP_NOT_FOUND


class TestEvidenceUpload:
    async def test_accepts_a_jpeg(self, client: AsyncClient, owner: dict[str, str]) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        analysis_id = await _open_analysis(client, owner, vehicle_id)

        response = await client.post(
            f"{ANALYSES_URL}/{analysis_id}/photos",
            files=_upload("front.jpg", _JPEG_BYTES),
            data={"kind": "exterior"},
            headers=owner,
        )

        body = response.json()
        assert response.status_code == _HTTP_CREATED
        assert body["content_type"] == "image/jpeg"
        assert body["kind"] == "exterior"
        assert body["size_bytes"] == len(_JPEG_BYTES)

    async def test_accepts_a_pdf_document(self, client: AsyncClient, owner: dict[str, str]) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        analysis_id = await _open_analysis(client, owner, vehicle_id)

        response = await client.post(
            f"{ANALYSES_URL}/{analysis_id}/photos",
            files=_upload("report.pdf", _PDF_BYTES, "application/pdf"),
            data={"kind": "document"},
            headers=owner,
        )

        assert response.status_code == _HTTP_CREATED
        assert response.json()["content_type"] == "application/pdf"

    async def test_the_declared_content_type_is_ignored(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        analysis_id = await _open_analysis(client, owner, vehicle_id)

        # PNG bytes declared as JPEG: the sniffer must win.
        response = await client.post(
            f"{ANALYSES_URL}/{analysis_id}/photos",
            files=_upload("photo.jpg", _PNG_BYTES, "image/jpeg"),
            headers=owner,
        )

        assert response.json()["content_type"] == "image/png"

    async def test_an_executable_is_rejected_regardless_of_name(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        analysis_id = await _open_analysis(client, owner, vehicle_id)

        response = await client.post(
            f"{ANALYSES_URL}/{analysis_id}/photos",
            files=_upload("innocent.jpg", _EXE_BYTES),
            headers=owner,
        )

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_an_oversized_file_is_rejected(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        analysis_id = await _open_analysis(client, owner, vehicle_id)
        too_big = _JPEG_BYTES + b"\x00" * container.settings.storage.max_upload_bytes

        response = await client.post(
            f"{ANALYSES_URL}/{analysis_id}/photos",
            files=_upload("huge.jpg", too_big),
            headers=owner,
        )

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_the_photo_limit_is_enforced(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        analysis_id = await _open_analysis(client, owner, vehicle_id)
        limit = container.settings.storage.max_photos_per_analysis

        for index in range(limit):
            response = await client.post(
                f"{ANALYSES_URL}/{analysis_id}/photos",
                files=_upload(f"photo-{index}.jpg", _JPEG_BYTES),
                headers=owner,
            )
            assert response.status_code == _HTTP_CREATED

        overflow = await client.post(
            f"{ANALYSES_URL}/{analysis_id}/photos",
            files=_upload("one-too-many.jpg", _JPEG_BYTES),
            headers=owner,
        )
        assert overflow.status_code == _HTTP_CONFLICT

    async def test_another_account_cannot_upload(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        analysis_id = await _open_analysis(client, owner, vehicle_id)

        response = await client.post(
            f"{ANALYSES_URL}/{analysis_id}/photos",
            files=_upload("front.jpg", _JPEG_BYTES),
            headers=intruder,
        )

        assert response.status_code == _HTTP_NOT_FOUND

    async def test_the_owner_can_download_their_upload(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        analysis_id = await _open_analysis(client, owner, vehicle_id)
        uploaded = await client.post(
            f"{ANALYSES_URL}/{analysis_id}/photos",
            files=_upload("front.jpg", _JPEG_BYTES),
            headers=owner,
        )
        photo_id = uploaded.json()["id"]

        response = await client.get(
            f"{ANALYSES_URL}/{analysis_id}/photos/{photo_id}", headers=owner
        )

        assert response.status_code == _HTTP_OK
        assert response.content == _JPEG_BYTES

    async def test_another_account_cannot_download(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        analysis_id = await _open_analysis(client, owner, vehicle_id)
        uploaded = await client.post(
            f"{ANALYSES_URL}/{analysis_id}/photos",
            files=_upload("front.jpg", _JPEG_BYTES),
            headers=owner,
        )
        photo_id = uploaded.json()["id"]

        response = await client.get(
            f"{ANALYSES_URL}/{analysis_id}/photos/{photo_id}", headers=intruder
        )

        assert response.status_code == _HTTP_NOT_FOUND


class TestRunningAnalyses:
    async def test_a_run_produces_a_complete_report(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner, vin="WVWZZZ1JZXW000001")
        analysis_id = await _open_analysis(client, owner, vehicle_id)
        for index in range(6):
            await client.post(
                f"{ANALYSES_URL}/{analysis_id}/photos",
                files=_upload(f"photo-{index}.jpg", _JPEG_BYTES),
                headers=owner,
            )

        response = await client.post(f"{ANALYSES_URL}/{analysis_id}/start", headers=owner)

        body = response.json()
        assert body["status"] == "completed"
        assert 0 <= body["trust_score"] <= 100
        assert body["risk_level"] in {"low", "medium", "high"}
        assert body["summary"]
        assert body["findings"]
        assert body["started_at"] is not None
        assert body["completed_at"] is not None

    async def test_a_completed_analysis_cannot_run_again(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        analysis_id = await _open_analysis(client, owner, vehicle_id)
        await client.post(f"{ANALYSES_URL}/{analysis_id}/start", headers=owner)

        response = await client.post(f"{ANALYSES_URL}/{analysis_id}/start", headers=owner)

        assert response.status_code == _HTTP_CONFLICT

    async def test_evidence_cannot_be_added_after_completion(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        analysis_id = await _open_analysis(client, owner, vehicle_id)
        await client.post(f"{ANALYSES_URL}/{analysis_id}/start", headers=owner)

        response = await client.post(
            f"{ANALYSES_URL}/{analysis_id}/photos",
            files=_upload("late.jpg", _JPEG_BYTES),
            headers=owner,
        )

        assert response.status_code == _HTTP_CONFLICT

    async def test_another_account_cannot_start_the_run(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        analysis_id = await _open_analysis(client, owner, vehicle_id)

        response = await client.post(f"{ANALYSES_URL}/{analysis_id}/start", headers=intruder)

        assert response.status_code == _HTTP_NOT_FOUND

    async def test_re_analysing_creates_an_independent_run(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        first_id = await _open_analysis(client, owner, vehicle_id)
        await client.post(f"{ANALYSES_URL}/{first_id}/start", headers=owner)

        second_id = await _open_analysis(client, owner, vehicle_id)

        assert second_id != first_id
        first = await client.get(f"{ANALYSES_URL}/{first_id}", headers=owner)
        second = await client.get(f"{ANALYSES_URL}/{second_id}", headers=owner)
        assert first.json()["status"] == "completed"
        assert second.json()["status"] == "pending"


class TestListingAnalyses:
    async def test_lists_only_the_callers_analyses(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        own_vehicle = await _save_vehicle(client, owner)
        other_vehicle = await _save_vehicle(client, intruder)
        await _open_analysis(client, owner, own_vehicle)
        await _open_analysis(client, intruder, other_vehicle)

        response = await client.get(ANALYSES_URL, headers=owner)

        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["vehicle_display_name"] == "BMW 320i"

    async def test_summaries_carry_the_score_after_completion(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        analysis_id = await _open_analysis(client, owner, vehicle_id)
        await client.post(f"{ANALYSES_URL}/{analysis_id}/start", headers=owner)

        response = await client.get(ANALYSES_URL, headers=owner)

        item = response.json()["items"][0]
        assert item["status"] == "completed"
        assert item["trust_score"] is not None
