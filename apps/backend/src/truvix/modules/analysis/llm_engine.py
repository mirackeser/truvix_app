"""LLM-enriched analysis engine.

Composition, not replacement: the rule-based engine always runs and its result
is the floor. When a chat model is configured, it reviews the vehicle and the
rule findings and may contribute additional findings, a refined summary and a
bounded score adjustment. If the model is unavailable, times out, or returns
anything that fails validation, the rule result ships unchanged — the user
always gets a report.

Privacy: the model never receives the plate or the VIN value. Only technical
specification fields leave the system.
"""

from __future__ import annotations

import json
from typing import Annotated, Final

from pydantic import BaseModel, Field

from truvix.modules.analysis.engine import (
    AnalysisEngine,
    EngineFinding,
    EngineResult,
    EvidenceSummary,
    risk_level_for,
)
from truvix.modules.analysis.models import (
    FINDING_DETAIL_MAX_LENGTH,
    FINDING_TITLE_MAX_LENGTH,
    MAX_SCORE,
    MIN_SCORE,
    FindingCategory,
    FindingSeverity,
)
from truvix.modules.vehicles.models import Vehicle
from truvix.shared.ai import ChatMessage, ChatModel, ChatRole
from truvix.shared.logging import get_logger

_logger = get_logger(__name__)

# The model may nudge the deterministic score, never overturn it.
MAX_SCORE_ADJUSTMENT: Final = 15
MAX_LLM_FINDINGS: Final = 6

_SYSTEM_PROMPT: Final = (
    "Sen Truvix'in ikinci el araç değerlendirme uzmanısın. Sana bir aracın "
    "teknik verileri ve kural tabanlı ön analiz bulguları verilecek. Görevin "
    "bu bilgileri gözden geçirip ek risk veya güçlü yön tespitleri yapmak.\n\n"
    "Kurallar:\n"
    "- Yalnızca verilen verilerden çıkarım yap; veri yoksa uydurma.\n"
    "- Türkçe yaz. Kısa, net ve alıcıya faydalı ol.\n"
    "- Yanıtın SADECE şu şemada bir JSON nesnesi olmalı:\n"
    '{"score_adjustment": int (-15..15), "summary": str, '
    '"findings": [{"category": "mileage|age|damage|maintenance|price|'
    'documentation|general", "severity": "positive|info|warning|critical", '
    '"title": str, "detail": str}]}'
)


class _LLMFinding(BaseModel):
    """One finding as the model is asked to produce it."""

    category: FindingCategory
    severity: FindingSeverity
    title: Annotated[str, Field(min_length=1, max_length=FINDING_TITLE_MAX_LENGTH)]
    detail: Annotated[str, Field(min_length=1, max_length=FINDING_DETAIL_MAX_LENGTH)]


class _LLMReview(BaseModel):
    """The complete response schema the model must satisfy."""

    score_adjustment: Annotated[int, Field(ge=-MAX_SCORE_ADJUSTMENT, le=MAX_SCORE_ADJUSTMENT)] = 0
    summary: Annotated[str, Field(min_length=1, max_length=1500)]
    findings: Annotated[list[_LLMFinding], Field(max_length=MAX_LLM_FINDINGS)] = []


class LLMEnrichedEngine:
    """Runs the base engine, then lets a chat model enrich the result."""

    def __init__(self, base: AnalysisEngine, model: ChatModel) -> None:
        """Initialise the engine.

        Args:
            base: The deterministic engine whose result is the floor.
            model: The chat model used for enrichment.
        """
        self._base = base
        self._model = model

    async def evaluate(self, vehicle: Vehicle, evidence: EvidenceSummary) -> EngineResult:
        """Produce the base report, enriched by the model when possible.

        Args:
            vehicle: The vehicle being analysed.
            evidence: Summary of the attached photos and documents.
        """
        base_result = await self._base.evaluate(vehicle, evidence)

        try:
            review = await self._request_review(vehicle, evidence, base_result)
        except Exception as exc:
            _logger.warning("llm_enrichment_skipped", reason=str(exc)[:200])
            return base_result

        return self._merge(base_result, review)

    async def _request_review(
        self, vehicle: Vehicle, evidence: EvidenceSummary, base: EngineResult
    ) -> _LLMReview:
        """Ask the model to review the base result and validate its reply."""
        completion = await self._model.complete(
            [
                ChatMessage(role=ChatRole.SYSTEM, content=_SYSTEM_PROMPT),
                ChatMessage(
                    role=ChatRole.USER,
                    content=json.dumps(
                        self._review_payload(vehicle, evidence, base),
                        ensure_ascii=False,
                    ),
                ),
            ],
            json_response=True,
        )
        return _LLMReview.model_validate(json.loads(completion.content))

    @staticmethod
    def _review_payload(
        vehicle: Vehicle, evidence: EvidenceSummary, base: EngineResult
    ) -> dict[str, object]:
        """Assemble the review request without identifying data.

        The plate and VIN values are intentionally absent: their presence is a
        boolean signal, their contents identify a real car and its owner.
        """
        return {
            "arac": {
                "marka": vehicle.make,
                "model": vehicle.model,
                "donanim": vehicle.variant,
                "yil": vehicle.model_year,
                "km": vehicle.mileage_km,
                "yakit": vehicle.fuel_type.value,
                "vites": vehicle.transmission.value,
                "kasa": vehicle.body_type.value if vehicle.body_type else None,
                "sehir": vehicle.city,
                "fiyat": str(vehicle.asking_price),
                "para_birimi": vehicle.currency.value,
                "vin_mevcut": vehicle.vin is not None,
            },
            "kanit": {
                "fotograf_sayisi": evidence.photo_count,
                "ekspertiz_raporu_var": evidence.has_document,
                "hasar_fotografi_var": evidence.has_damage_photo,
            },
            "on_analiz": {
                "skor": base.trust_score,
                "bulgular": [
                    {"onem": f.severity.value, "baslik": f.title, "detay": f.detail}
                    for f in base.findings
                ],
            },
        }

    @staticmethod
    def _merge(base: EngineResult, review: _LLMReview) -> EngineResult:
        """Fold a validated review into the base result under the guardrails."""
        adjusted = max(MIN_SCORE, min(MAX_SCORE, base.trust_score + review.score_adjustment))

        # Model findings are appended after the deterministic ones and capped;
        # duplicates by title are dropped so the list stays readable.
        seen_titles = {finding.title for finding in base.findings}
        extra = tuple(
            EngineFinding(
                category=finding.category,
                severity=finding.severity,
                title=finding.title,
                detail=finding.detail,
            )
            for finding in review.findings
            if finding.title not in seen_titles
        )

        _logger.info(
            "llm_enrichment_applied",
            score_adjustment=review.score_adjustment,
            extra_findings=len(extra),
        )
        return EngineResult(
            trust_score=adjusted,
            risk_level=risk_level_for(adjusted),
            summary=review.summary,
            findings=base.findings + extra,
        )
