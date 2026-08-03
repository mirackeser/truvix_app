"""Integration tests for the garage: vehicles, price tracking and collections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from truvix.modules.vehicles.models import PriceSnapshot, Vehicle
from truvix.shared.container import ApplicationContainer

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/register"
VEHICLES_URL = "/api/v1/vehicles"
COLLECTIONS_URL = "/api/v1/collections"

_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_NO_CONTENT = 204
_HTTP_UNAUTHORIZED = 401
_HTTP_NOT_FOUND = 404
_HTTP_CONFLICT = 409
_HTTP_UNPROCESSABLE = 422

_PASSWORD = "a-sufficiently-long-passphrase"


def _vehicle_payload(**overrides: Any) -> dict[str, Any]:
    """Build a valid vehicle payload, mirroring the BMW card in the designs."""
    payload: dict[str, Any] = {
        "make": "BMW",
        "model": "320i",
        "variant": "M Sport",
        "model_year": 2021,
        "mileage_km": 67000,
        "fuel_type": "petrol",
        "transmission": "automatic",
        "body_type": "sedan",
        "plate": "34 ABC 123",
        "asking_price": "1250000.00",
        "currency": "TRY",
        "city": "Istanbul",
    }
    payload.update(overrides)
    return payload


async def _sign_up(client: AsyncClient, email: str) -> dict[str, str]:
    """Register an account and return an Authorization header for it."""
    response = await client.post(
        REGISTER_URL,
        json={"email": email, "password": _PASSWORD, "full_name": "Test Kullanici"},
    )
    assert response.status_code == _HTTP_CREATED, response.text
    token = response.json()["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _save_vehicle(
    client: AsyncClient, headers: dict[str, str], **overrides: Any
) -> dict[str, Any]:
    """Save a vehicle and return the decoded response body."""
    response = await client.post(
        VEHICLES_URL, json=_vehicle_payload(**overrides), headers=headers
    )
    assert response.status_code == _HTTP_CREATED, response.text
    body: dict[str, Any] = response.json()
    return body


@pytest.fixture
async def owner(client: AsyncClient) -> dict[str, str]:
    """Authorization header for the primary test account."""
    return await _sign_up(client, "owner@truvix.app")


@pytest.fixture
async def intruder(client: AsyncClient) -> dict[str, str]:
    """Authorization header for a second, unrelated account."""
    return await _sign_up(client, "intruder@truvix.app")


class TestSavingVehicles:
    async def test_saves_a_vehicle_to_the_garage(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        body = await _save_vehicle(client, owner)

        assert body["make"] == "BMW"
        assert body["display_name"] == "BMW 320i M Sport"
        assert body["model_year"] == 2021
        assert Decimal(body["asking_price"]) == Decimal("1250000.00")
        assert body["is_favourite"] is False

    async def test_plate_is_normalised(self, client: AsyncClient, owner: dict[str, str]) -> None:
        body = await _save_vehicle(client, owner, plate="34 abc 123")

        assert body["plate"] == "34ABC123"

    async def test_vin_is_normalised(self, client: AsyncClient, owner: dict[str, str]) -> None:
        body = await _save_vehicle(client, owner, vin="wvwzzz1jzxw000001")

        assert body["vin"] == "WVWZZZ1JZXW000001"

    async def test_the_asking_price_becomes_the_first_observation(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        await _save_vehicle(client, owner)

        async with container.database.transaction() as session:
            snapshots = (await session.scalars(select(PriceSnapshot))).all()

        assert len(snapshots) == 1
        assert snapshots[0].price == Decimal("1250000.00")

    @pytest.mark.parametrize(
        "overrides",
        [
            {"model_year": 1800},
            {"model_year": 3000},
            {"mileage_km": -1},
            {"asking_price": "0"},
            {"plate": "not-a-plate"},
            {"vin": "TOO-SHORT"},
            {"vin": "IOQIOQIOQIOQIOQIO"},
            {"fuel_type": "nuclear"},
            {"listing_url": "not-a-url"},
        ],
        ids=[
            "year_too_early",
            "year_in_future",
            "negative_mileage",
            "zero_price",
            "bad_plate",
            "short_vin",
            "vin_with_forbidden_letters",
            "unknown_fuel",
            "bad_url",
        ],
    )
    async def test_invalid_payloads_are_rejected(
        self, client: AsyncClient, owner: dict[str, str], overrides: dict[str, Any]
    ) -> None:
        response = await client.post(
            VEHICLES_URL, json=_vehicle_payload(**overrides), headers=owner
        )

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_saving_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(VEHICLES_URL, json=_vehicle_payload())

        assert response.status_code == _HTTP_UNAUTHORIZED


class TestOwnershipIsolation:
    """One account must never be able to observe or touch another's garage."""

    async def test_another_account_cannot_read_the_vehicle(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)

        response = await client.get(f"{VEHICLES_URL}/{vehicle['id']}", headers=intruder)

        assert response.status_code == _HTTP_NOT_FOUND

    async def test_another_account_cannot_update_the_vehicle(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)

        response = await client.patch(
            f"{VEHICLES_URL}/{vehicle['id']}", json={"mileage_km": 1}, headers=intruder
        )

        assert response.status_code == _HTTP_NOT_FOUND

    async def test_another_account_cannot_delete_the_vehicle(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)

        response = await client.delete(f"{VEHICLES_URL}/{vehicle['id']}", headers=intruder)

        assert response.status_code == _HTTP_NOT_FOUND

    async def test_another_account_cannot_record_a_price(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)

        response = await client.post(
            f"{VEHICLES_URL}/{vehicle['id']}/prices",
            json={"price": "1.00"},
            headers=intruder,
        )

        assert response.status_code == _HTTP_NOT_FOUND

    async def test_another_account_cannot_read_the_price_history(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)

        response = await client.get(f"{VEHICLES_URL}/{vehicle['id']}/prices", headers=intruder)

        assert response.status_code == _HTTP_NOT_FOUND

    async def test_the_garage_list_only_shows_own_vehicles(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        await _save_vehicle(client, owner)
        await _save_vehicle(client, intruder, make="Audi", model="A4")

        response = await client.get(VEHICLES_URL, headers=owner)

        assert response.status_code == _HTTP_OK
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["vehicle"]["make"] == "BMW"

    async def test_a_vehicle_cannot_be_filed_into_another_accounts_collection(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)
        collection = await client.post(
            COLLECTIONS_URL, json={"name": "Intruder list"}, headers=intruder
        )
        collection_id = collection.json()["id"]

        response = await client.put(
            f"{COLLECTIONS_URL}/{collection_id}/vehicles/{vehicle['id']}", headers=intruder
        )

        assert response.status_code == _HTTP_NOT_FOUND


class TestReadingAndUpdating:
    async def test_reading_marks_the_vehicle_as_viewed(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)
        assert vehicle["last_viewed_at"] is None

        response = await client.get(f"{VEHICLES_URL}/{vehicle['id']}", headers=owner)

        assert response.json()["last_viewed_at"] is not None

    async def test_a_partial_update_leaves_other_fields_alone(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)

        response = await client.patch(
            f"{VEHICLES_URL}/{vehicle['id']}", json={"mileage_km": 71000}, headers=owner
        )

        body = response.json()
        assert body["mileage_km"] == 71000
        assert body["make"] == "BMW"
        assert Decimal(body["asking_price"]) == Decimal("1250000.00")

    async def test_marking_a_favourite(self, client: AsyncClient, owner: dict[str, str]) -> None:
        vehicle = await _save_vehicle(client, owner)

        response = await client.patch(
            f"{VEHICLES_URL}/{vehicle['id']}", json={"is_favourite": True}, headers=owner
        )

        assert response.json()["is_favourite"] is True

    async def test_changing_the_price_records_an_observation(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        vehicle = await _save_vehicle(client, owner)

        await client.patch(
            f"{VEHICLES_URL}/{vehicle['id']}", json={"asking_price": "1225000.00"}, headers=owner
        )

        async with container.database.transaction() as session:
            snapshots = (await session.scalars(select(PriceSnapshot))).all()
        assert len(snapshots) == 2

    async def test_an_unchanged_price_records_nothing(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        vehicle = await _save_vehicle(client, owner)

        await client.patch(
            f"{VEHICLES_URL}/{vehicle['id']}", json={"asking_price": "1250000.00"}, headers=owner
        )

        async with container.database.transaction() as session:
            snapshots = (await session.scalars(select(PriceSnapshot))).all()
        assert len(snapshots) == 1

    async def test_deleting_hides_the_vehicle_but_keeps_the_row(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        vehicle = await _save_vehicle(client, owner)

        deleted = await client.delete(f"{VEHICLES_URL}/{vehicle['id']}", headers=owner)

        assert deleted.status_code == _HTTP_NO_CONTENT
        follow_up = await client.get(f"{VEHICLES_URL}/{vehicle['id']}", headers=owner)
        assert follow_up.status_code == _HTTP_NOT_FOUND

        async with container.database.transaction() as session:
            stored = (await session.scalars(select(Vehicle))).all()
        assert len(stored) == 1
        assert stored[0].deleted_at is not None


class TestPriceTracking:
    async def test_recording_a_price_updates_the_card(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)

        await client.post(
            f"{VEHICLES_URL}/{vehicle['id']}/prices", json={"price": "1225000.00"}, headers=owner
        )

        card = await client.get(f"{VEHICLES_URL}/{vehicle['id']}", headers=owner)
        assert Decimal(card.json()["asking_price"]) == Decimal("1225000.00")

    async def test_the_trend_reports_a_drop(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)
        await client.post(
            f"{VEHICLES_URL}/{vehicle['id']}/prices", json={"price": "1225000.00"}, headers=owner
        )

        response = await client.get(f"{VEHICLES_URL}/{vehicle['id']}/prices", headers=owner)

        trend = response.json()["trend"]
        assert Decimal(trend["absolute_change"]) == Decimal("-25000.00")
        assert Decimal(trend["percentage_change"]) == Decimal("-2.00")
        assert trend["observation_count"] == 2

    async def test_a_single_observation_reports_no_change(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)

        response = await client.get(f"{VEHICLES_URL}/{vehicle['id']}/prices", headers=owner)

        trend = response.json()["trend"]
        assert trend["absolute_change"] is None
        assert trend["previous_price"] is None

    async def test_a_future_observation_is_rejected(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)
        tomorrow = (datetime.now(UTC) + timedelta(days=1)).isoformat()

        response = await client.post(
            f"{VEHICLES_URL}/{vehicle['id']}/prices",
            json={"price": "1.00", "observed_at": tomorrow},
            headers=owner,
        )

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_several_observations_on_one_day_collapse_to_one_point(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)
        for price in ("1240000.00", "1235000.00", "1230000.00"):
            await client.post(
                f"{VEHICLES_URL}/{vehicle['id']}/prices", json={"price": price}, headers=owner
            )

        response = await client.get(f"{VEHICLES_URL}/{vehicle['id']}/prices", headers=owner)

        points = response.json()["points"]
        assert len(points) == 1
        assert Decimal(points[0]["price"]) == Decimal("1230000.00")


class TestGarageFilters:
    async def test_the_favourites_tab(self, client: AsyncClient, owner: dict[str, str]) -> None:
        favourite = await _save_vehicle(client, owner)
        await _save_vehicle(client, owner, make="Audi", model="A4", plate="06 XYZ 456")
        await client.patch(
            f"{VEHICLES_URL}/{favourite['id']}", json={"is_favourite": True}, headers=owner
        )

        response = await client.get(VEHICLES_URL, params={"filter": "favourites"}, headers=owner)

        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["vehicle"]["make"] == "BMW"

    async def test_the_price_dropped_tab(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        dropped = await _save_vehicle(client, owner)
        await _save_vehicle(client, owner, make="Audi", model="A4", plate="06 XYZ 456")
        await client.post(
            f"{VEHICLES_URL}/{dropped['id']}/prices", json={"price": "1225000.00"}, headers=owner
        )

        response = await client.get(
            VEHICLES_URL, params={"filter": "price_dropped"}, headers=owner
        )

        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["vehicle"]["make"] == "BMW"

    async def test_a_rising_price_is_not_a_drop(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)
        await client.post(
            f"{VEHICLES_URL}/{vehicle['id']}/prices", json={"price": "1300000.00"}, headers=owner
        )

        response = await client.get(
            VEHICLES_URL, params={"filter": "price_dropped"}, headers=owner
        )

        assert response.json()["total"] == 0

    async def test_the_viewed_today_tab(self, client: AsyncClient, owner: dict[str, str]) -> None:
        viewed = await _save_vehicle(client, owner)
        await _save_vehicle(client, owner, make="Audi", model="A4", plate="06 XYZ 456")
        await client.get(f"{VEHICLES_URL}/{viewed['id']}", headers=owner)

        response = await client.get(VEHICLES_URL, params={"filter": "viewed_today"}, headers=owner)

        assert response.json()["total"] == 1

    async def test_sorting_by_price(self, client: AsyncClient, owner: dict[str, str]) -> None:
        await _save_vehicle(client, owner, asking_price="1250000.00")
        await _save_vehicle(
            client, owner, make="Honda", model="Civic", plate="06 XYZ 456", asking_price="900000.00"
        )

        response = await client.get(VEHICLES_URL, params={"sort": "price_asc"}, headers=owner)

        prices = [Decimal(item["vehicle"]["asking_price"]) for item in response.json()["items"]]
        assert prices == sorted(prices)

    async def test_pagination_reports_the_full_total(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        for index in range(3):
            await _save_vehicle(client, owner, plate=f"34 AB {100 + index}")

        response = await client.get(VEHICLES_URL, params={"page_size": 2}, headers=owner)

        body = response.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2
        assert body["has_next"] is True


class TestGarageStats:
    async def test_counts_match_the_tabs(self, client: AsyncClient, owner: dict[str, str]) -> None:
        favourite = await _save_vehicle(client, owner)
        dropped = await _save_vehicle(client, owner, make="Audi", model="A4", plate="06 XYZ 456")
        await client.patch(
            f"{VEHICLES_URL}/{favourite['id']}", json={"is_favourite": True}, headers=owner
        )
        await client.post(
            f"{VEHICLES_URL}/{dropped['id']}/prices", json={"price": "1000000.00"}, headers=owner
        )
        await client.get(f"{VEHICLES_URL}/{favourite['id']}", headers=owner)

        response = await client.get(f"{VEHICLES_URL}/stats", headers=owner)

        body = response.json()
        assert body["total"] == 2
        assert body["favourites"] == 1
        assert body["price_dropped"] == 1
        assert body["viewed_today"] == 1

    async def test_a_deleted_vehicle_leaves_the_counts(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)
        await client.delete(f"{VEHICLES_URL}/{vehicle['id']}", headers=owner)

        response = await client.get(f"{VEHICLES_URL}/stats", headers=owner)

        assert response.json()["total"] == 0


class TestCollections:
    async def test_creating_and_listing(self, client: AsyncClient, owner: dict[str, str]) -> None:
        created = await client.post(
            COLLECTIONS_URL, json={"name": "Karsilastirilacaklar"}, headers=owner
        )

        assert created.status_code == _HTTP_CREATED
        listed = await client.get(COLLECTIONS_URL, headers=owner)
        assert listed.json()[0]["name"] == "Karsilastirilacaklar"
        assert listed.json()[0]["vehicle_count"] == 0

    async def test_duplicate_names_are_rejected(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        await client.post(COLLECTIONS_URL, json={"name": "Favoriler"}, headers=owner)

        response = await client.post(COLLECTIONS_URL, json={"name": "Favoriler"}, headers=owner)

        assert response.status_code == _HTTP_CONFLICT

    async def test_two_accounts_may_use_the_same_collection_name(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        await client.post(COLLECTIONS_URL, json={"name": "Favoriler"}, headers=owner)

        response = await client.post(COLLECTIONS_URL, json={"name": "Favoriler"}, headers=intruder)

        assert response.status_code == _HTTP_CREATED

    async def test_adding_and_removing_a_vehicle(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)
        collection = await client.post(COLLECTIONS_URL, json={"name": "Kisa liste"}, headers=owner)
        collection_id = collection.json()["id"]

        added = await client.put(
            f"{COLLECTIONS_URL}/{collection_id}/vehicles/{vehicle['id']}", headers=owner
        )
        assert added.status_code == _HTTP_NO_CONTENT

        listed = await client.get(COLLECTIONS_URL, headers=owner)
        assert listed.json()[0]["vehicle_count"] == 1

        removed = await client.delete(
            f"{COLLECTIONS_URL}/{collection_id}/vehicles/{vehicle['id']}", headers=owner
        )
        assert removed.status_code == _HTTP_NO_CONTENT

    async def test_adding_the_same_vehicle_twice_is_rejected(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)
        collection = await client.post(COLLECTIONS_URL, json={"name": "Kisa liste"}, headers=owner)
        collection_id = collection.json()["id"]
        await client.put(
            f"{COLLECTIONS_URL}/{collection_id}/vehicles/{vehicle['id']}", headers=owner
        )

        response = await client.put(
            f"{COLLECTIONS_URL}/{collection_id}/vehicles/{vehicle['id']}", headers=owner
        )

        assert response.status_code == _HTTP_CONFLICT

    async def test_deleting_a_collection_keeps_the_vehicles(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle = await _save_vehicle(client, owner)
        collection = await client.post(COLLECTIONS_URL, json={"name": "Kisa liste"}, headers=owner)
        collection_id = collection.json()["id"]
        await client.put(
            f"{COLLECTIONS_URL}/{collection_id}/vehicles/{vehicle['id']}", headers=owner
        )

        await client.delete(f"{COLLECTIONS_URL}/{collection_id}", headers=owner)

        still_there = await client.get(f"{VEHICLES_URL}/{vehicle['id']}", headers=owner)
        assert still_there.status_code == _HTTP_OK

    async def test_another_account_cannot_delete_the_collection(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        collection = await client.post(COLLECTIONS_URL, json={"name": "Kisa liste"}, headers=owner)

        response = await client.delete(
            f"{COLLECTIONS_URL}/{collection.json()['id']}", headers=intruder
        )

        assert response.status_code == _HTTP_NOT_FOUND
