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
