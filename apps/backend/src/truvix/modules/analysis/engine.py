"""Evaluation engines that turn a vehicle and its evidence into a report.

``AnalysisEngine`` is the seam where intelligence plugs in. The rule-based
engine below is the deterministic baseline: it scores what can be computed from
the data the user actually provided, with no external calls and no guesswork.
The LLM-backed engine in the AI service will be a second implementation of the
same protocol, and the two can run side by side — rules as the floor, the model
as the enrichment — without the analysis workflow changing at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from truvix.modules.analysis.models import (
    MAX_SCORE,
    MIN_SCORE,
    FindingCategory,
    FindingSeverity,
    PhotoKind,
    RiskLevel,
)
from truvix.modules.vehicles.models import Vehicle

# Score bands mirroring the report screen: 80+ renders as "Düşük Risk".
LOW_RISK_THRESHOLD = 80
MEDIUM_RISK_THRESHOLD = 60

_BASE_SCORE = 65

# Age scoring.
_NEARLY_NEW_MAX_AGE_YEARS = 3
_MODERATE_MAX_AGE_YEARS = 8
_OLD_VEHICLE_AGE_YEARS = 16
_NEARLY_NEW_BONUS = 8
_OLD_VEHICLE_PENALTY = 10

# Annual mileage scoring, in kilometres per year of age.
_LOW_ANNUAL_KM = 15_000
_HIGH_ANNUAL_KM = 30_000
_LOW_MILEAGE_BONUS = 10
_HIGH_MILEAGE_PENALTY = 12

# Evidence scoring.
_GOOD_PHOTO_COUNT = 6
_SOME_PHOTO_COUNT = 3
_GOOD_PHOTO_BONUS = 8
_SOME_PHOTO_BONUS = 4
_NO_PHOTO_PENALTY = 6
_VIN_BONUS = 5
_DOCUMENT_BONUS = 6
_DAMAGE_PHOTO_PENALTY = 8


@dataclass(frozen=True, slots=True)
class EvidenceSummary:
    """What the user attached to the analysis, summarised for scoring."""

    photo_count: int
    photo_kinds: frozenset[PhotoKind]

    @property
    def has_document(self) -> bool:
        """Whether an expertise report or similar document was attached."""
        return PhotoKind.DOCUMENT in self.photo_kinds

    @property
    def has_damage_photo(self) -> bool:
        """Whether the uploader explicitly marked a photo as showing damage."""
        return PhotoKind.DAMAGE in self.photo_kinds


@dataclass(frozen=True, slots=True)
class EngineFinding:
    """One finding produced by an engine, ordered most important first."""

    category: FindingCategory
    severity: FindingSeverity
    title: str
    detail: str


@dataclass(frozen=True, slots=True)
class EngineResult:
    """The complete outcome of one engine run."""

    trust_score: int
    risk_level: RiskLevel
    summary: str
    findings: tuple[EngineFinding, ...]


class AnalysisEngine(Protocol):
    """Interface every evaluation engine implements."""

    async def evaluate(self, vehicle: Vehicle, evidence: EvidenceSummary) -> EngineResult:
        """Produce a report for the vehicle given the attached evidence."""
        ...


def risk_level_for(score: int) -> RiskLevel:
    """Band a trust score the way the report screen presents it.

    Args:
        score: A trust score between 0 and 100.
    """
    if score >= LOW_RISK_THRESHOLD:
        return RiskLevel.LOW
    if score >= MEDIUM_RISK_THRESHOLD:
        return RiskLevel.MEDIUM
    return RiskLevel.HIGH


class RuleBasedEngine:
    """Deterministic scoring from the vehicle's own data.

    Every adjustment is explained by a finding, so the score the user sees is
    fully accounted for by the list underneath it — the transparency the
    reference apps lack.
    """

    async def evaluate(self, vehicle: Vehicle, evidence: EvidenceSummary) -> EngineResult:
        """Score the vehicle and explain each adjustment.

        Args:
            vehicle: The vehicle being analysed.
            evidence: Summary of the attached photos and documents.
        """
        findings: list[EngineFinding] = []
        score = _BASE_SCORE

        score += self._score_age(vehicle, findings)
        score += self._score_mileage(vehicle, findings)
        score += self._score_evidence(evidence, findings)
        score += self._score_documentation(vehicle, evidence, findings)

        bounded = max(MIN_SCORE, min(MAX_SCORE, score))
        level = risk_level_for(bounded)

        ordered = tuple(sorted(findings, key=self._display_rank))
        return EngineResult(
            trust_score=bounded,
            risk_level=level,
            summary=self._summarise(bounded, level, evidence),
            findings=ordered,
        )

    @staticmethod
    def _vehicle_age_years(vehicle: Vehicle) -> int:
        """The vehicle's age in whole years, never negative."""
        return max(datetime.now(UTC).year - vehicle.model_year, 0)

    def _score_age(self, vehicle: Vehicle, findings: list[EngineFinding]) -> int:
        """Score the vehicle's age band."""
        age = self._vehicle_age_years(vehicle)
        if age <= _NEARLY_NEW_MAX_AGE_YEARS:
            findings.append(
                EngineFinding(
                    category=FindingCategory.AGE,
                    severity=FindingSeverity.POSITIVE,
                    title="Araç yaşı düşük",
                    detail=f"{vehicle.model_year} model araç {age} yaşında; yeni sayılır.",
                )
            )
            return _NEARLY_NEW_BONUS
        if age >= _OLD_VEHICLE_AGE_YEARS:
            findings.append(
                EngineFinding(
                    category=FindingCategory.AGE,
                    severity=FindingSeverity.WARNING,
                    title="Araç yaşı yüksek",
                    detail=(
                        f"Araç {age} yaşında. Bu yaştaki araçlarda bakım ve yedek parça "
                        "maliyetleri belirgin şekilde artar."
                    ),
                )
            )
            return -_OLD_VEHICLE_PENALTY
        if age > _MODERATE_MAX_AGE_YEARS:
            findings.append(
                EngineFinding(
                    category=FindingCategory.AGE,
                    severity=FindingSeverity.INFO,
                    title="Orta yaşlı araç",
                    detail=f"Araç {age} yaşında; yaş grubuna göre normal aralıkta.",
                )
            )
        return 0

    def _score_mileage(self, vehicle: Vehicle, findings: list[EngineFinding]) -> int:
        """Score kilometres relative to the vehicle's age."""
        age = self._vehicle_age_years(vehicle)
        annual_km = vehicle.mileage_km if age == 0 else vehicle.mileage_km / age

        if annual_km < _LOW_ANNUAL_KM:
            findings.append(
                EngineFinding(
                    category=FindingCategory.MILEAGE,
                    severity=FindingSeverity.POSITIVE,
                    title="Kilometre ortalamanın altında",
                    detail=(
                        f"Yıllık ortalama {annual_km:,.0f} km kullanım, {_LOW_ANNUAL_KM:,} km "
                        "olan piyasa ortalamasının altında."
                    ),
                )
            )
            return _LOW_MILEAGE_BONUS
        if annual_km > _HIGH_ANNUAL_KM:
            findings.append(
                EngineFinding(
                    category=FindingCategory.MILEAGE,
                    severity=FindingSeverity.WARNING,
                    title="Kilometre ortalamanın üzerinde",
                    detail=(
                        f"Yıllık ortalama {annual_km:,.0f} km kullanım yoğun kullanıma işaret "
                        "eder; motor ve şanzıman durumunu kontrol ettirin."
                    ),
                )
            )
            return -_HIGH_MILEAGE_PENALTY
        return 0

    def _score_evidence(self, evidence: EvidenceSummary, findings: list[EngineFinding]) -> int:
        """Score the quantity of visual evidence provided."""
        adjustment = 0
        if evidence.photo_count >= _GOOD_PHOTO_COUNT:
            adjustment += _GOOD_PHOTO_BONUS
        elif evidence.photo_count >= _SOME_PHOTO_COUNT:
            adjustment += _SOME_PHOTO_BONUS
        elif evidence.photo_count == 0:
            findings.append(
                EngineFinding(
                    category=FindingCategory.GENERAL,
                    severity=FindingSeverity.INFO,
                    title="Fotoğraf eklenmedi",
                    detail=(
                        "Analize fotoğraf eklenmedi. Fotoğraflar değerlendirmenin "
                        "isabetini artırır."
                    ),
                )
            )
            adjustment -= _NO_PHOTO_PENALTY

        if evidence.has_damage_photo:
            findings.append(
                EngineFinding(
                    category=FindingCategory.DAMAGE,
                    severity=FindingSeverity.WARNING,
                    title="Hasar fotoğrafı işaretlendi",
                    detail=(
                        "Yüklenen fotoğraflardan en az biri hasar olarak işaretlendi. "
                        "Hasarın kapsamını ekspertizde doğrulatın."
                    ),
                )
            )
            adjustment -= _DAMAGE_PHOTO_PENALTY
        return adjustment

    def _score_documentation(
        self, vehicle: Vehicle, evidence: EvidenceSummary, findings: list[EngineFinding]
    ) -> int:
        """Score identifying and documentary completeness."""
        adjustment = 0
        if vehicle.vin is not None:
            findings.append(
                EngineFinding(
                    category=FindingCategory.DOCUMENTATION,
                    severity=FindingSeverity.POSITIVE,
                    title="Şasi numarası doğrulanabilir",
                    detail="VIN girildi; aracın kimliği resmi kayıtlarla eşleştirilebilir.",
                )
            )
            adjustment += _VIN_BONUS
        else:
            findings.append(
                EngineFinding(
                    category=FindingCategory.DOCUMENTATION,
                    severity=FindingSeverity.INFO,
                    title="Şasi numarası eksik",
                    detail="VIN girilmedi. VIN ile geçmiş sorgulaması yapılamaz.",
                )
            )

        if evidence.has_document:
            findings.append(
                EngineFinding(
                    category=FindingCategory.MAINTENANCE,
                    severity=FindingSeverity.POSITIVE,
                    title="Ekspertiz raporu eklendi",
                    detail="Rapor, değerlendirmeye belge desteği sağlar.",
                )
            )
            adjustment += _DOCUMENT_BONUS
        return adjustment

    @staticmethod
    def _summarise(score: int, level: RiskLevel, evidence: EvidenceSummary) -> str:
        """Write the report's one-paragraph verdict."""
        if level is RiskLevel.LOW:
            verdict = (
                "Araç mevcut verilere göre düşük riskli görünüyor. "
                "Satın alma öncesi standart kontroller yeterli olacaktır."
            )
        elif level is RiskLevel.MEDIUM:
            verdict = (
                "Araçta dikkat edilmesi gereken noktalar var. Belirtilen risk "
                "faktörlerini ekspertizde özellikle kontrol ettirin."
            )
        else:
            verdict = (
                "Araç mevcut verilere göre yüksek riskli görünüyor. Kapsamlı bir "
                "ekspertiz yaptırmadan karar vermeyin."
            )
        evidence_note = (
            "" if evidence.photo_count > 0 else " Fotoğraf eklenmesi analizi güçlendirir."
        )
        return f"Güven skoru {score}/100. {verdict}{evidence_note}"

    @staticmethod
    def _display_rank(finding: EngineFinding) -> int:
        """Order findings the way the report lists them: risks first."""
        order = {
            FindingSeverity.CRITICAL: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.POSITIVE: 2,
            FindingSeverity.INFO: 3,
        }
        return order[finding.severity]
