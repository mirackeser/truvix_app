"""Inspecting a vehicle's photographs with a vision model.

This is the step that makes an uploaded photo worth uploading. Until now the
engine only counted files; here they are actually looked at, and what the model
sees becomes findings the report can show and justify.

Two properties are enforced and are the reason this lives in its own module:

1. **The inspection never fails an analysis.** A provider outage, an unreadable
   file or a reply that does not validate all degrade to "no visual findings",
   because a report from the data the user typed is still worth having.
2. **What is sent is bounded and stated.** At most a fixed number of images,
   each reduced to a bounded size, and the prompt says plainly that the model
   is looking at a used car. Photographs are the most sensitive thing the app
   handles, so the decision about what leaves the system is written down rather
   than implied.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Final

from pydantic import BaseModel, Field, ValidationError

from truvix.modules.analysis.engine import EngineFinding
from truvix.modules.analysis.models import (
    FINDING_DETAIL_MAX_LENGTH,
    FINDING_TITLE_MAX_LENGTH,
    AnalysisPhoto,
    FindingCategory,
    FindingSeverity,
    PhotoKind,
)
from truvix.shared.ai import ChatMessage, ChatModel, ChatRole, ImageAttachment
from truvix.shared.logging import get_logger
from truvix.shared.storage import LocalFileStorage
from truvix.shared.storage.images import prepare_for_vision

_logger = get_logger(__name__)

# Each image costs tokens, and a used-car listing's useful angles are covered
# well before this. Beyond it the marginal photograph adds cost, not insight.
MAX_IMAGES_INSPECTED: Final = 6

# The model may nudge the score, never overturn the deterministic one.
MAX_VISION_SCORE_ADJUSTMENT: Final = 12
MAX_VISION_FINDINGS: Final = 6

_SYSTEM_PROMPT: Final = (
    "Sen ikinci el araç ekspertizi konusunda uzman bir görsel değerlendirme "
    "asistanısın. Sana bir aracın satış fotoğrafları verilecek.\n\n"
    "Görevin fotoğraflarda GÖRDÜĞÜN somut şeyleri raporlamak:\n"
    "- Boya farkı, çizik, ezik, pas, çatlak cam, uyumsuz panel aralığı\n"
    "- Lastik diş derinliği, jant hasarı\n"
    "- İç döşeme aşınması, gösterge panelindeki uyarı ışıkları\n"
    "- Motor bölmesinde sızıntı veya aşırı kir izleri\n\n"
    "Kurallar:\n"
    "- SADECE fotoğrafta görebildiğin şeyleri yaz. Göremediğin bir şey "
    "hakkında yorum yapma, tahmin etme.\n"
    "- Fotoğraf bulanık, karanlık veya yetersizse bunu belirt; uydurma.\n"
    "- Aracın plakasını, kişilerin yüzünü veya çevredeki özel bilgileri "
    "raporlama; bunlar değerlendirmenin konusu değil.\n"
    "- Türkçe yaz. Kısa ve somut ol.\n"
    "- Yanıtın SADECE şu şemada bir JSON nesnesi olmalı:\n"
    '{"score_adjustment": int (-12..12), "photo_quality": "good|limited|poor", '
    '"findings": [{"category": "damage|maintenance|general", '
    '"severity": "positive|info|warning|critical", "title": str, "detail": str}]}'
)


class _VisionFinding(BaseModel):
    """One observation as the model is asked to produce it."""

    category: FindingCategory
    severity: FindingSeverity
    title: Annotated[str, Field(min_length=1, max_length=FINDING_TITLE_MAX_LENGTH)]
    detail: Annotated[str, Field(min_length=1, max_length=FINDING_DETAIL_MAX_LENGTH)]


class _VisionReport(BaseModel):
    """The complete response schema the model must satisfy."""

    score_adjustment: Annotated[
        int, Field(ge=-MAX_VISION_SCORE_ADJUSTMENT, le=MAX_VISION_SCORE_ADJUSTMENT)
    ] = 0
    photo_quality: str = "limited"
    findings: Annotated[list[_VisionFinding], Field(max_length=MAX_VISION_FINDINGS)] = []


@dataclass(frozen=True, slots=True)
class VisualInspection:
    """What the model saw, folded into the shape the engine consumes."""

    findings: tuple[EngineFinding, ...]
    score_adjustment: int
    images_inspected: int

    @staticmethod
    def none() -> VisualInspection:
        """The result when no inspection happened."""
        return VisualInspection(findings=(), score_adjustment=0, images_inspected=0)

    @property
    def happened(self) -> bool:
        """Whether any image was actually looked at."""
        return self.images_inspected > 0


class PhotoInspector:
    """Looks at an analysis's photographs and reports what it sees."""

    def __init__(self, *, model: ChatModel, storage: LocalFileStorage) -> None:
        """Initialise the inspector.

        Args:
            model: The vision-capable chat model.
            storage: Where the uploaded photographs live.
        """
        self._model = model
        self._storage = storage

    async def inspect(self, photos: list[AnalysisPhoto]) -> VisualInspection:
        """Inspect the photographs attached to an analysis.

        Args:
            photos: The attached files, in upload order.

        Returns:
            What was seen, or an empty inspection when nothing could be.
        """
        attachments = self._load(photos)
        if not attachments:
            return VisualInspection.none()

        try:
            report = await self._request(attachments)
        # Catching broadly is this seam's contract: no failure of the
        # inspection may prevent a report being produced.
        except Exception as exc:
            _logger.warning("vision_inspection_skipped", reason=str(exc)[:200])
            return VisualInspection.none()

        findings = tuple(
            EngineFinding(
                category=finding.category,
                severity=finding.severity,
                title=finding.title,
                detail=finding.detail,
            )
            for finding in report.findings
        )
        _logger.info(
            "vision_inspection_completed",
            images=len(attachments),
            findings=len(findings),
            score_adjustment=report.score_adjustment,
            photo_quality=report.photo_quality,
        )
        return VisualInspection(
            findings=findings,
            score_adjustment=report.score_adjustment,
            images_inspected=len(attachments),
        )

    def _load(self, photos: list[AnalysisPhoto]) -> list[ImageAttachment]:
        """Read and prepare the images worth inspecting.

        Documents are skipped: a PDF expertise report is text, and sending it
        to a vision prompt asks the wrong question of the wrong model.
        """
        candidates = [photo for photo in photos if photo.kind is not PhotoKind.DOCUMENT]
        # Damage photographs are put first so that, when the limit truncates
        # the set, the images most likely to matter are the ones sent.
        candidates.sort(key=lambda photo: photo.kind is not PhotoKind.DAMAGE)

        attachments: list[ImageAttachment] = []
        for photo in candidates[:MAX_IMAGES_INSPECTED]:
            try:
                path = self._storage.open(photo.storage_key)
            except FileNotFoundError:
                _logger.warning("vision_photo_missing", storage_key=photo.storage_key)
                continue

            prepared = prepare_for_vision(path.read_bytes())
            if prepared is None:
                continue

            attachments.append(ImageAttachment(data=prepared.data, media_type=prepared.media_type))
        return attachments

    async def _request(self, attachments: list[ImageAttachment]) -> _VisionReport:
        """Ask the model to describe the images and validate its reply."""
        completion = await self._model.complete(
            [
                ChatMessage(role=ChatRole.SYSTEM, content=_SYSTEM_PROMPT),
                ChatMessage(
                    role=ChatRole.USER,
                    content=(
                        f"Bu ikinci el aracın {len(attachments)} fotoğrafını incele "
                        "ve gördüğün somut bulguları raporla."
                    ),
                    images=tuple(attachments),
                ),
            ],
            json_response=True,
        )
        try:
            return _VisionReport.model_validate(json.loads(completion.content))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"vision reply did not validate: {exc}") from exc
