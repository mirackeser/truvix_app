from __future__ import annotations

from fastapi import APIRouter, Request

from truvix_ai.analysis.schemas import AnalysisRequest, AnalysisResponse, PhotoInput
from truvix_ai.analysis.engine import RuleBasedEngine
from truvix_ai.analysis.llm_engine import LLMEnrichedEngine
from truvix_ai.analysis.vision import PhotoInspector, VisualInspection
from truvix_ai.core.chat import ChatModel

router = APIRouter(prefix="/api/v1/analyze", tags=["Analysis"])

@router.post("/", response_model=AnalysisResponse)
async def analyze_vehicle(request: Request, body: AnalysisRequest) -> AnalysisResponse:
    chat_model: ChatModel | None = getattr(request.app.state, "chat_model", None)
    
    if chat_model:
        engine = LLMEnrichedEngine(chat_model)
        return await engine.evaluate(body.vehicle, body.photos)
    else:
        # Fallback to pure rules
        engine = RuleBasedEngine()
        res = engine.evaluate(body.vehicle, body.photos)
        from truvix_ai.analysis.schemas import RiskFindingOut
        
        return AnalysisResponse(
            trust_score=res.score,
            risk_level=res.risk_level,
            summary="Yapay zeka analizi devrede değil, kural bazlı değerlendirme yapıldı.",
            findings=[
                RiskFindingOut(
                    category=f.category,
                    severity=f.severity,
                    title=f.title,
                    detail=f.detail
                ) for f in res.findings
            ],
            images_inspected=0,
            ai_enhanced=False
        )

@router.post("/photos")
async def analyze_photos(request: Request, photos: list[PhotoInput]) -> dict:
    chat_model: ChatModel | None = getattr(request.app.state, "chat_model", None)
    
    if chat_model:
        inspector = PhotoInspector(chat_model)
        result = await inspector.inspect(photos)
        return {
            "score_adjustment": result.score_adjustment,
            "images_inspected": result.images_inspected,
            "findings": [f.model_dump() for f in result.findings]
        }
    
    return {"score_adjustment": 0, "images_inspected": 0, "findings": []}
