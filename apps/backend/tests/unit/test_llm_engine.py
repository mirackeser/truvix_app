"""Tests for the LLM-enriched engine's guardrails and degradation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from tests.unit.test_analysis_engine import _evidence, _vehicle
from truvix.modules.analysis.engine import RuleBasedEngine
from truvix.modules.analysis.llm_engine import MAX_SCORE_ADJUSTMENT, LLMEnrichedEngine
from truvix.modules.vehicles.models import Currency, FuelType, Transmission, Vehicle
from truvix.shared.ai import ChatCompletion, ChatMessage
from truvix.shared.errors import ExternalServiceError


class ScriptedChatModel:
    """A chat model that replies with a fixed body and records its input."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.received: list[list[ChatMessage]] = []
        self.calls = 0

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        json_response: bool = False,
        max_output_tokens: int | None = None,
    ) -> ChatCompletion:
        self.calls += 1
        self.received.append(messages)
        return ChatCompletion(content=self.reply, input_tokens=10, output_tokens=10)


class FailingChatModel:
    """A chat model whose provider is down."""

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        json_response: bool = False,
        max_output_tokens: int | None = None,
    ) -> ChatCompletion:
        raise ExternalServiceError("provider down", service="openai")


def _valid_review(**overrides: object) -> str:
    """A review reply the schema accepts."""
    body: dict[str, object] = {
        "score_adjustment": 5,
        "summary": "Araç genel olarak iyi durumda görünüyor.",
        "findings": [
            {
                "category": "price",
                "severity": "info",
                "title": "Fiyat segment ortalamasına yakın",
                "detail": "İstenen fiyat benzer araçlarla uyumlu görünüyor.",
            }
        ],
    }
    body.update(overrides)
    return json.dumps(body)


class TestEnrichment:
    async def test_a_valid_review_adjusts_the_score_and_adds_findings(self) -> None:
        model = ScriptedChatModel(_valid_review())
        engine = LLMEnrichedEngine(RuleBasedEngine(), model)
        base = await RuleBasedEngine().evaluate(_vehicle(), _evidence(count=4))

        result = await engine.evaluate(_vehicle(), _evidence(count=4))

        assert result.trust_score == base.trust_score + 5
        assert any(f.title == "Fiyat segment ortalamasına yakın" for f in result.findings)
        assert result.summary == "Araç genel olarak iyi durumda görünüyor."

    async def test_base_findings_are_never_lost(self) -> None:
        model = ScriptedChatModel(_valid_review())
        engine = LLMEnrichedEngine(RuleBasedEngine(), model)
        base = await RuleBasedEngine().evaluate(_vehicle(), _evidence())

        result = await engine.evaluate(_vehicle(), _evidence())

        base_titles = {finding.title for finding in base.findings}
        result_titles = {finding.title for finding in result.findings}
        assert base_titles <= result_titles


class TestGuardrails:
    async def test_an_out_of_range_adjustment_is_rejected_entirely(self) -> None:
        model = ScriptedChatModel(_valid_review(score_adjustment=90))
        engine = LLMEnrichedEngine(RuleBasedEngine(), model)
        base = await RuleBasedEngine().evaluate(_vehicle(), _evidence())

        result = await engine.evaluate(_vehicle(), _evidence())

        # Validation fails, so the whole review is discarded, not clamped:
        # a model that ignores the bounds forfeits its say.
        assert result.trust_score == base.trust_score
        assert result.summary == base.summary

    async def test_malformed_json_falls_back_to_the_rule_result(self) -> None:
        model = ScriptedChatModel("this is not json at all")
        engine = LLMEnrichedEngine(RuleBasedEngine(), model)
        base = await RuleBasedEngine().evaluate(_vehicle(), _evidence())

        result = await engine.evaluate(_vehicle(), _evidence())

        assert result == base

    async def test_a_provider_outage_falls_back_to_the_rule_result(self) -> None:
        engine = LLMEnrichedEngine(RuleBasedEngine(), FailingChatModel())
        base = await RuleBasedEngine().evaluate(_vehicle(), _evidence())

        result = await engine.evaluate(_vehicle(), _evidence())

        assert result == base

    async def test_too_many_findings_are_rejected(self) -> None:
        finding = {
            "category": "general",
            "severity": "info",
            "title": "Tekrarlanan bulgu",
            "detail": "Ayni bulgu.",
        }
        model = ScriptedChatModel(_valid_review(findings=[finding] * 10))
        engine = LLMEnrichedEngine(RuleBasedEngine(), model)
        base = await RuleBasedEngine().evaluate(_vehicle(), _evidence())

        result = await engine.evaluate(_vehicle(), _evidence())

        assert result == base

    async def test_the_adjusted_score_never_leaves_bounds(self) -> None:
        year = datetime.now(UTC).year
        # A weak vehicle near the floor plus the maximum negative adjustment.
        weak = _vehicle(model_year=year - 30, mileage_km=1_500_000)
        model = ScriptedChatModel(_valid_review(score_adjustment=-MAX_SCORE_ADJUSTMENT))
        engine = LLMEnrichedEngine(RuleBasedEngine(), model)

        result = await engine.evaluate(weak, _evidence())

        assert 0 <= result.trust_score <= 100


class TestPrivacy:
    async def test_plate_and_vin_values_never_reach_the_model(self) -> None:
        model = ScriptedChatModel(_valid_review())
        engine = LLMEnrichedEngine(RuleBasedEngine(), model)
        vehicle = Vehicle(
            make="BMW",
            model="320i",
            model_year=2021,
            mileage_km=67_000,
            fuel_type=FuelType.PETROL,
            transmission=Transmission.AUTOMATIC,
            asking_price=Decimal("1250000.00"),
            currency=Currency.TRY,
            plate="34ABC123",
            vin="WVWZZZ1JZXW000001",
        )

        await engine.evaluate(vehicle, _evidence())

        sent = " ".join(message.content for message in model.received[0])
        assert "34ABC123" not in sent
        assert "WVWZZZ1JZXW000001" not in sent
        # Presence is still signalled, because it matters to the assessment.
        assert "vin_mevcut" in sent
