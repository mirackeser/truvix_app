"""Integration tests for the probes, error envelope and security headers."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from truvix import __version__
from truvix.shared.errors import PROBLEM_CONTENT_TYPE

pytestmark = pytest.mark.integration


class TestLiveness:
    async def test_reports_the_running_version(self, client: AsyncClient) -> None:
        response = await client.get("/health/live")

        assert response.status_code == 200
        assert response.json() == {"status": "alive", "version": __version__}


class TestReadiness:
    async def test_reports_every_dependency_as_reachable(self, client: AsyncClient) -> None:
        response = await client.get("/health/ready")

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert {dep["name"] for dep in payload["dependencies"]} == {"postgresql", "redis"}
        assert all(dep["healthy"] for dep in payload["dependencies"])


class TestErrorEnvelope:
    async def test_unknown_route_returns_a_problem_document(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/no-such-endpoint")

        assert response.status_code == 404
        assert response.headers["content-type"].startswith(PROBLEM_CONTENT_TYPE)
        payload = response.json()
        assert payload["code"] == "not_found"
        assert payload["status"] == 404
        assert payload["instance"] == "/api/v1/no-such-endpoint"
        assert payload["requestId"]


class TestRequestCorrelation:
    async def test_a_request_id_is_generated_when_absent(self, client: AsyncClient) -> None:
        response = await client.get("/health/live")

        assert response.headers["x-request-id"]

    async def test_an_inbound_request_id_is_preserved(self, client: AsyncClient) -> None:
        supplied = "01931f4e-6d2c-7a11-9f3e-0242ac120002"

        response = await client.get("/health/live", headers={"X-Request-ID": supplied})

        assert response.headers["x-request-id"] == supplied


class TestSecurityHeaders:
    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("x-content-type-options", "nosniff"),
            ("x-frame-options", "DENY"),
            ("referrer-policy", "strict-origin-when-cross-origin"),
            ("cross-origin-opener-policy", "same-origin"),
        ],
    )
    async def test_hardening_headers_are_present(
        self, client: AsyncClient, header: str, expected: str
    ) -> None:
        response = await client.get("/health/live")

        assert response.headers[header] == expected

    async def test_hsts_is_not_sent_outside_production(self, client: AsyncClient) -> None:
        response = await client.get("/health/live")

        assert "strict-transport-security" not in response.headers


class TestTransactionBoundary:
    """The transaction has to close before the client is told anything."""

    async def test_a_write_is_readable_immediately_afterwards(self, client: AsyncClient) -> None:
        """The defect this guards was real, not theoretical.

        With the transaction in a `yield` dependency, FastAPI committed it after
        the response had been sent: running an analysis and immediately asking
        for the notifications it produced missed them about one time in twelve.
        """
        registered = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "read-after-write@truvix.app",
                "password": "a-sufficiently-long-passphrase",
                "full_name": "Okuma Yazma",
            },
        )
        assert registered.status_code == 201, registered.text
        headers = {"Authorization": f"Bearer {registered.json()['tokens']['access_token']}"}

        created = await client.post(
            "/api/v1/vehicles",
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
        assert created.status_code == 201, created.text

        listed = await client.get("/api/v1/vehicles?page=1&page_size=5", headers=headers)
        assert listed.json()["total"] == 1

    async def test_a_rejected_request_leaves_nothing_behind(self, client: AsyncClient) -> None:
        """The exception became a response further in, so nothing propagates
        to the middleware to trigger a rollback on its own — it has to notice
        the status itself."""
        registered = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "nothing-behind@truvix.app",
                "password": "a-sufficiently-long-passphrase",
                "full_name": "Geri Alma",
            },
        )
        headers = {"Authorization": f"Bearer {registered.json()['tokens']['access_token']}"}

        refused = await client.post(
            "/api/v1/vehicles",
            json={
                "make": "",
                "model": "",
                "model_year": 1800,
                "mileage_km": -5,
                "fuel_type": "petrol",
                "transmission": "automatic",
                "asking_price": "0",
            },
            headers=headers,
        )
        assert refused.status_code == 422

        listed = await client.get("/api/v1/vehicles?page=1&page_size=5", headers=headers)
        assert listed.json()["total"] == 0
