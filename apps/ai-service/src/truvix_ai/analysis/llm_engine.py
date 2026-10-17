from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel

from truvix_ai.core.chat import ChatModel, ChatMessage, ChatRole
from truvix_ai.observability.logging import get_logger
from truvix_ai.analysis.schemas import (
    VehicleData, PhotoInput, AnalysisResponse, RiskFindingOut, RiskLevel
)
from truvix_ai.analysis.engine import RuleBasedEngine
from truvix_ai.analysis.vision import PhotoInspector
from truvix_ai.guardrails.prompts import ANALYSIS_SYSTEM_PROMPT

logger = get_logger(__name__)

MAX_SCORE_ADJUSTMENT: Final[int] = 15


class _LLMReview(BaseModel):
    score_adjustment: int
    summary: str
    findings: list[RiskFindingOut]


class LLMEnrichedEngine:
    """Coordinates rules, vision, and LLM reasoning."""

    def __init__(self, chat_model: ChatModel) -> None:
        self._rules = RuleBasedEngine()
        self._vision = PhotoInspector(chat_model)
        self._model = chat_model

    async def evaluate(self, vehicle: VehicleData, photos: list[PhotoInput]) -> AnalysisResponse:
        rule_result = self._rules.evaluate(vehicle, photos)
        vision_result = await self._vision.inspect(photos)

        payload = self._review_payload(vehicle, rule_result.score)
        
        try:
            completion = await self._model.complete(
                messages=[
                    ChatMessage(role=ChatRole.SYSTEM, content=ANALYSIS_SYSTEM_PROMPT),
                    ChatMessage(role=ChatRole.USER, content=json.dumps(payload))
                ],
                response_schema=_LLMReview.model_json_schema()
            )
            llm_review = _LLMReview.model_validate_json(completion.message.content)
            
            score_adj = max(-MAX_SCORE_ADJUSTMENT, min(MAX_SCORE_ADJUSTMENT, llm_review.score_adjustment))
            final_score = max(0, min(100, rule_result.score + vision_result.score_adjustment + score_adj))
            
            all_findings = [
                RiskFindingOut(category=f.category, severity=f.severity, title=f.title, detail=f.detail)
                for f in rule_result.findings
            ]
            all_findings.extend([
                RiskFindingOut(category=f.category, severity=f.severity, title=f.title, detail=f.detail)
                for f in vision_result.findings
            ])
            all_findings.extend(llm_review.findings[:6])
            
            return AnalysisResponse(
                trust_score=final_score,
                risk_level=self._risk_level_for(final_score),
                summary=llm_review.summary,
                findings=all_findings,
                images_inspected=vision_result.images_inspected,
                ai_enhanced=True
            )
            
        except Exception as e:
            logger.warning("LLM evaluation failed, degrading gracefully", error=str(e), exc_info=True)
            
            final_score = max(0, min(100, rule_result.score + vision_result.score_adjustment))
            all_findings = [
                RiskFindingOut(category=f.category, severity=f.severity, title=f.title, detail=f.detail)
                for f in rule_result.findings
            ]
            all_findings.extend([
                RiskFindingOut(category=f.category, severity=f.severity, title=f.title, detail=f.detail)
                for f in vision_result.findings
            ])
            
            return AnalysisResponse(
                trust_score=final_score,
                risk_level=self._risk_level_for(final_score),
                summary="Sistem geçici olarak yapay zeka analizini tamamlayamadı. Temel değerlendirme sonuçları gösteriliyor.",
                findings=all_findings,
                images_inspected=vision_result.images_inspected,
                ai_enhanced=False
            )

    def _review_payload(self, vehicle: VehicleData, base_score: int) -> dict:
        data = vehicle.model_dump(exclude={'vin', 'plate'})
        data['base_score'] = base_score
        return data

    def _risk_level_for(self, score: int) -> RiskLevel:
        if score >= 80:
            return RiskLevel.LOW
        elif score >= 60:
            return RiskLevel.MEDIUM
        return RiskLevel.HIGH
