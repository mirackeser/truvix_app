"""Tests for the rule-based analysis engine."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from truvix.modules.analysis.engine import (
    LOW_RISK_THRESHOLD,
    MEDIUM_RISK_THRESHOLD,
    EvidenceSummary,
    RuleBasedEngine,
    risk_level_for,
)
from truvix.modules.analysis.models import FindingSeverity, PhotoKind, RiskLevel
from truvix.modules.vehicles.models import Currency, FuelType, Transmission, Vehicle


def _vehicle(**overrides: object) -> Vehicle:
    """Build an unsaved vehicle for engine input."""
    values: dict[str, object] = {
        "make": "BMW",
        "model": "320i",
        "model_year": datetime.now(UTC).year - 2,
        "mileage_km": 20_000,
        "fuel_type": FuelType.PETROL,
        "transmission": Transmission.AUTOMATIC,
        "asking_price": Decimal("1250000.00"),
        "currency": Currency.TRY,
    }
    values.update(overrides)
    return Vehicle(**values)


def _evidence(count: int = 0, kinds: frozenset[PhotoKind] | None = None) -> EvidenceSummary:
    """Build an evidence summary."""
    return EvidenceSummary(photo_count=count, photo_kinds=kinds or frozenset())


@pytest.fixture
def engine() -> RuleBasedEngine:
    return RuleBasedEngine()


class TestRiskBanding:
    def test_bands_match_the_report_screen(self) -> None:
        assert risk_level_for(LOW_RISK_THRESHOLD) is RiskLevel.LOW
        assert risk_level_for(MEDIUM_RISK_THRESHOLD) is RiskLevel.MEDIUM
        assert risk_level_for(MEDIUM_RISK_THRESHOLD - 1) is RiskLevel.HIGH


class TestScoring:
    async def test_a_strong_vehicle_scores_low_risk(self, engine: RuleBasedEngine) -> None:
        vehicle = _vehicle(vin="WVWZZZ1JZXW000001")
        evidence = _evidence(count=8, kinds=frozenset({PhotoKind.EXTERIOR, PhotoKind.DOCUMENT}))

        result = await engine.evaluate(vehicle, evidence)

        assert result.risk_level is RiskLevel.LOW
        assert result.trust_score >= LOW_RISK_THRESHOLD

    async def test_an_old_heavily_used_vehicle_scores_worse(self, engine: RuleBasedEngine) -> None:
        year = datetime.now(UTC).year
        strong = await engine.evaluate(_vehicle(), _evidence(count=6))
        weak = await engine.evaluate(
            _vehicle(model_year=year - 20, mileage_km=700_000), _evidence()
        )

        assert weak.trust_score < strong.trust_score

    async def test_scores_are_deterministic(self, engine: RuleBasedEngine) -> None:
        vehicle = _vehicle()
        evidence = _evidence(count=4)

        first = await engine.evaluate(vehicle, evidence)
        second = await engine.evaluate(vehicle, evidence)

        assert first.trust_score == second.trust_score
        assert first.findings == second.findings

    async def test_score_stays_within_bounds(self, engine: RuleBasedEngine) -> None:
        year = datetime.now(UTC).year
        worst = await engine.evaluate(
            _vehicle(model_year=year - 30, mileage_km=1_500_000),
            _evidence(kinds=frozenset({PhotoKind.DAMAGE})),
        )
        best = await engine.evaluate(
            _vehicle(vin="WVWZZZ1JZXW000001", mileage_km=1_000),
            _evidence(count=10, kinds=frozenset({PhotoKind.DOCUMENT})),
        )

        assert 0 <= worst.trust_score <= 100
        assert 0 <= best.trust_score <= 100


class TestFindings:
    async def test_low_mileage_produces_a_positive_finding(self, engine: RuleBasedEngine) -> None:
        result = await engine.evaluate(_vehicle(mileage_km=10_000), _evidence())

        titles = [finding.title for finding in result.findings]
        assert "Kilometre ortalamanın altında" in titles

    async def test_a_damage_photo_produces_a_warning(self, engine: RuleBasedEngine) -> None:
        result = await engine.evaluate(
            _vehicle(), _evidence(count=2, kinds=frozenset({PhotoKind.DAMAGE}))
        )

        warnings = [f for f in result.findings if f.severity is FindingSeverity.WARNING]
        assert any("Hasar" in f.title for f in warnings)

    async def test_missing_vin_is_reported_as_information(self, engine: RuleBasedEngine) -> None:
        result = await engine.evaluate(_vehicle(vin=None), _evidence())

        info = [f for f in result.findings if f.severity is FindingSeverity.INFO]
        assert any("Şasi" in f.title for f in info)

    async def test_findings_list_risks_before_positives(self, engine: RuleBasedEngine) -> None:
        year = datetime.now(UTC).year
        result = await engine.evaluate(
            _vehicle(model_year=year - 20, mileage_km=800_000, vin="WVWZZZ1JZXW000001"),
            _evidence(count=6),
        )

        severities = [finding.severity for finding in result.findings]
        first_positive = severities.index(FindingSeverity.POSITIVE)
        assert all(
            severity in {FindingSeverity.WARNING, FindingSeverity.CRITICAL}
            for severity in severities[:first_positive]
        )

    async def test_the_summary_carries_the_score(self, engine: RuleBasedEngine) -> None:
        result = await engine.evaluate(_vehicle(), _evidence(count=4))

        assert f"{result.trust_score}/100" in result.summary
