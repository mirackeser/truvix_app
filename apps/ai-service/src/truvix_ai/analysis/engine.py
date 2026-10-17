from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

from truvix_ai.analysis.schemas import FindingCategory, FindingSeverity, RiskLevel, VehicleData, PhotoInput, PhotoKind

BASE_SCORE: Final[int] = 65


def format_number(num: int) -> str:
    """Format number with dot separators for Turkish locale."""
    return f"{num:,}".replace(",", ".")


@dataclass(frozen=True, slots=True)
class EvidenceSummary:
    total_photos: int
    has_damage: bool
    has_document: bool


@dataclass(frozen=True, slots=True)
class EngineFinding:
    category: FindingCategory
    severity: FindingSeverity
    title: str
    detail: str


@dataclass(frozen=True, slots=True)
class EngineResult:
    score: int
    risk_level: RiskLevel
    findings: list[EngineFinding]


class AnalysisEngine(Protocol):
    """Protocol for rule-based analysis engine."""
    
    def evaluate(self, vehicle: VehicleData, photos: list[PhotoInput]) -> EngineResult:
        ...


class RuleBasedEngine:
    """Evaluates vehicle data based on hardcoded rules."""
    
    def evaluate(self, vehicle: VehicleData, photos: list[PhotoInput]) -> EngineResult:
        score = BASE_SCORE
        findings: list[EngineFinding] = []
        
        # Age logic
        import datetime
        current_year = datetime.datetime.now().year
        age = current_year - vehicle.model_year
        if age <= 3:
            score += 8
            findings.append(EngineFinding(
                category=FindingCategory.AGE,
                severity=FindingSeverity.POSITIVE,
                title="Yeni Araç",
                detail=f"Araç henüz {age} yaşında, nispeten yeni."
            ))
        elif age >= 16:
            score -= 10
            findings.append(EngineFinding(
                category=FindingCategory.AGE,
                severity=FindingSeverity.WARNING,
                title="Yaşlı Araç",
                detail=f"Araç {age} yaşında. Düzenli bakım önemlidir."
            ))
            
        # Mileage logic
        if age > 0:
            yearly_km = vehicle.mileage_km / age
            if yearly_km < 15000:
                score += 10
                findings.append(EngineFinding(
                    category=FindingCategory.MILEAGE,
                    severity=FindingSeverity.POSITIVE,
                    title="Düşük Kilometre",
                    detail=f"Araç yaşına göre az kullanılmış. (Yıllık ~{format_number(int(yearly_km))} km)"
                ))
            elif yearly_km > 30000:
                score -= 12
                findings.append(EngineFinding(
                    category=FindingCategory.MILEAGE,
                    severity=FindingSeverity.WARNING,
                    title="Yüksek Kilometre",
                    detail=f"Araç yaşına göre çok kullanılmış. (Yıllık ~{format_number(int(yearly_km))} km)"
                ))
                
        # Evidence logic
        evidence = EvidenceSummary(
            total_photos=len(photos),
            has_damage=any(p.kind == PhotoKind.DAMAGE for p in photos),
            has_document=any(p.kind == PhotoKind.DOCUMENT for p in photos)
        )
        
        if evidence.total_photos >= 6:
            score += 8
            findings.append(EngineFinding(
                category=FindingCategory.DOCUMENTATION,
                severity=FindingSeverity.POSITIVE,
                title="Zengin Görsel",
                detail="İlan için detaylı görseller eklenmiş."
            ))
        elif evidence.total_photos >= 3:
            score += 4
        elif evidence.total_photos == 0:
            score -= 6
            findings.append(EngineFinding(
                category=FindingCategory.DOCUMENTATION,
                severity=FindingSeverity.WARNING,
                title="Görsel Eksikliği",
                detail="İlanda hiç fotoğraf bulunmuyor."
            ))
            
        if evidence.has_damage:
            score -= 8
            findings.append(EngineFinding(
                category=FindingCategory.DAMAGE,
                severity=FindingSeverity.WARNING,
                title="Hasar Kaydı/İzi",
                detail="Hasar ile ilgili görseller tespit edildi."
            ))
            
        if vehicle.vin:
            score += 5
            findings.append(EngineFinding(
                category=FindingCategory.DOCUMENTATION,
                severity=FindingSeverity.POSITIVE,
                title="Şasi Numarası Belirtilmiş",
                detail="Araç şasi numarası (VIN) beyan edilmiş."
            ))
            
        if evidence.has_document:
            score += 6
            findings.append(EngineFinding(
                category=FindingCategory.DOCUMENTATION,
                severity=FindingSeverity.POSITIVE,
                title="Ekspertiz/Belge",
                detail="Araç belgeleri görsellere eklenmiş."
            ))
            
        final_score = max(0, min(100, score))
        return EngineResult(
            score=final_score,
            risk_level=self._risk_level_for(final_score),
            findings=findings
        )
        
    def _risk_level_for(self, score: int) -> RiskLevel:
        if score >= 80:
            return RiskLevel.LOW
        elif score >= 60:
            return RiskLevel.MEDIUM
        return RiskLevel.HIGH
