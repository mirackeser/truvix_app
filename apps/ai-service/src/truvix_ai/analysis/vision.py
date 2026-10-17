from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel

from truvix_ai.core.chat import ChatModel, ChatMessage, ChatRole, ImageAttachment
from truvix_ai.core.image import prepare_for_vision
from truvix_ai.core.errors import ExternalServiceError
from truvix_ai.observability.logging import get_logger
from truvix_ai.analysis.schemas import PhotoInput, PhotoKind, FindingCategory, FindingSeverity
from truvix_ai.guardrails.prompts import VISION_SYSTEM_PROMPT

logger = get_logger(__name__)

MAX_IMAGES_INSPECTED: Final[int] = 6


class _VisionFinding(BaseModel):
    category: FindingCategory
    severity: FindingSeverity
    title: str
    detail: str


class _VisionReport(BaseModel):
    score_adjustment: int
    photo_quality: str
    findings: list[_VisionFinding]


@dataclass(frozen=True, slots=True)
class VisualInspection:
    findings: list[_VisionFinding]
    score_adjustment: int
    images_inspected: int

    @staticmethod
    def none() -> VisualInspection:
        return VisualInspection(findings=[], score_adjustment=0, images_inspected=0)


class PhotoInspector:
    """Uses vision model to assess vehicle photos."""
    
    def __init__(self, model: ChatModel) -> None:
        self._model = model

    async def inspect(self, photos: list[PhotoInput]) -> VisualInspection:
        if not photos:
            return VisualInspection.none()

        try:
            # Filter and sort photos
            inspection_photos = [p for p in photos if p.kind != PhotoKind.DOCUMENT]
            inspection_photos.sort(key=lambda p: p.kind == PhotoKind.DAMAGE, reverse=True)
            inspection_photos = inspection_photos[:MAX_IMAGES_INSPECTED]

            if not inspection_photos:
                return VisualInspection.none()

            attachments = []
            for photo in inspection_photos:
                resized_b64 = prepare_for_vision(photo.data_b64)
                attachments.append(ImageAttachment(data=resized_b64, media_type=photo.media_type))

            message = ChatMessage(
                role=ChatRole.USER,
                content="Lütfen aşağıdaki araç görsellerini inceleyip raporlayın.",
                images=attachments
            )
            
            completion = await self._model.complete(
                messages=[
                    ChatMessage(role=ChatRole.SYSTEM, content=VISION_SYSTEM_PROMPT),
                    message
                ],
                response_schema=_VisionReport.model_json_schema()
            )

            report = _VisionReport.model_validate_json(completion.message.content)
            
            return VisualInspection(
                findings=report.findings,
                score_adjustment=max(-12, min(12, report.score_adjustment)),
                images_inspected=len(inspection_photos)
            )
            
        except Exception as e:
            logger.warning("Visual inspection failed", error=str(e), exc_info=True)
            return VisualInspection.none()
