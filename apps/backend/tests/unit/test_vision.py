"""Tests for photo preparation and the vision inspection."""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from truvix.modules.analysis.engine import EvidenceSummary, RuleBasedEngine
from truvix.modules.analysis.llm_engine import LLMEnrichedEngine
from truvix.modules.analysis.models import AnalysisPhoto, FindingSeverity, PhotoKind
from truvix.modules.analysis.vision import (
    MAX_IMAGES_INSPECTED,
    MAX_VISION_SCORE_ADJUSTMENT,
    PhotoInspector,
)
from truvix.shared.ai import ChatCompletion, ChatMessage
from truvix.shared.errors import ExternalServiceError
from truvix.shared.storage import LocalFileStorage
from truvix.shared.storage.images import MAX_DIMENSION, prepare_for_vision


def make_image(width: int, height: int, *, fmt: str = "JPEG") -> bytes:
    """Render a solid-colour image of the given size."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(20, 180, 120)).save(buffer, format=fmt)
    return buffer.getvalue()


class TestImagePreparation:
    def test_a_large_photograph_is_reduced(self) -> None:
        # A phone photograph is thousands of pixels wide; sending that is paid
        # for and then discarded, because the model downsamples anyway.
        prepared = prepare_for_vision(make_image(4032, 3024))

        assert prepared is not None
        assert max(prepared.width, prepared.height) == MAX_DIMENSION

    def test_reduction_preserves_the_aspect_ratio(self) -> None:
        prepared = prepare_for_vision(make_image(4000, 2000))

        assert prepared is not None
        assert prepared.width == MAX_DIMENSION
        assert prepared.height == MAX_DIMENSION // 2

    def test_a_small_photograph_is_not_enlarged(self) -> None:
        prepared = prepare_for_vision(make_image(320, 240))

        assert prepared is not None
        assert (prepared.width, prepared.height) == (320, 240)

    def test_reduction_shrinks_the_payload(self) -> None:
        original = make_image(4032, 3024, fmt="PNG")

        prepared = prepare_for_vision(original)

        assert prepared is not None
        assert len(prepared.data) < len(original)

    def test_every_output_is_a_jpeg(self) -> None:
        # One output format keeps the media type the provider is told about
        # correct regardless of what the phone produced.
        prepared = prepare_for_vision(make_image(800, 600, fmt="PNG"))

        assert prepared is not None
        assert prepared.media_type == "image/jpeg"

    def test_bytes_that_are_not_an_image_are_refused(self) -> None:
        # A single unreadable file must not fail an analysis, so this returns
        # None for the caller to skip rather than raising.
        assert prepare_for_vision(b"this is not an image") is None

    def test_an_empty_payload_is_refused(self) -> None:
        assert prepare_for_vision(b"") is None


class RecordingVisionModel:
    """A model that answers with a fixed body and records what it was sent."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.received: list[list[ChatMessage]] = []

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        json_response: bool = False,
        max_output_tokens: int | None = None,
    ) -> ChatCompletion:
        self.received.append(messages)
        return ChatCompletion(content=self.reply, input_tokens=100, output_tokens=50)

    @property
    def images_sent(self) -> int:
        return sum(len(message.images) for message in self.received[0])


class FailingVisionModel:
    """A model whose provider is down."""

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        json_response: bool = False,
        max_output_tokens: int | None = None,
    ) -> ChatCompletion:
        raise ExternalServiceError("provider down", service="openai")


def valid_report(**overrides: Any) -> str:
    """A vision reply the schema accepts."""
    body: dict[str, Any] = {
        "score_adjustment": -5,
        "photo_quality": "good",
        "findings": [
            {
                "category": "damage",
                "severity": "warning",
                "title": "Ön tamponda çizik",
                "detail": "Ön tamponun sağ alt köşesinde belirgin çizik görünüyor.",
            }
        ],
    }
    body.update(overrides)
    return json.dumps(body)


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path)


def store_photo(
    storage: LocalFileStorage,
    *,
    kind: PhotoKind = PhotoKind.EXTERIOR,
    payload: bytes | None = None,
) -> AnalysisPhoto:
    """Persist an image and return the record that points at it."""
    data = payload if payload is not None else make_image(1600, 1200)
    stored = storage.save(
        io.BytesIO(data), namespace="analysis", extension="jpg", max_bytes=10_000_000
    )
    return AnalysisPhoto(
        analysis_id=uuid.uuid7(),
        kind=kind,
        storage_key=stored.key,
        content_type="image/jpeg",
        size_bytes=stored.size_bytes,
        original_filename="photo.jpg",
    )


class TestPhotoInspection:
    async def test_a_valid_report_becomes_findings(self, storage: LocalFileStorage) -> None:
        model = RecordingVisionModel(valid_report())
        inspector = PhotoInspector(model=model, storage=storage)

        inspection = await inspector.inspect([store_photo(storage)])

        assert inspection.happened
        assert inspection.images_inspected == 1
        assert inspection.score_adjustment == -5
        assert len(inspection.findings) == 1
        assert inspection.findings[0].severity is FindingSeverity.WARNING

    async def test_the_images_actually_reach_the_model(self, storage: LocalFileStorage) -> None:
        model = RecordingVisionModel(valid_report())
        inspector = PhotoInspector(model=model, storage=storage)

        await inspector.inspect([store_photo(storage), store_photo(storage)])

        assert model.images_sent == 2

    async def test_no_photos_means_no_inspection(self, storage: LocalFileStorage) -> None:
        model = RecordingVisionModel(valid_report())
        inspector = PhotoInspector(model=model, storage=storage)

        inspection = await inspector.inspect([])

        assert not inspection.happened
        assert model.received == []

    async def test_documents_are_not_sent_to_a_vision_prompt(
        self, storage: LocalFileStorage
    ) -> None:
        # A PDF expertise report is text; showing it to a vision prompt asks
        # the wrong question of the wrong model.
        model = RecordingVisionModel(valid_report())
        inspector = PhotoInspector(model=model, storage=storage)

        inspection = await inspector.inspect([store_photo(storage, kind=PhotoKind.DOCUMENT)])

        assert not inspection.happened

    async def test_the_number_of_images_is_capped(self, storage: LocalFileStorage) -> None:
        model = RecordingVisionModel(valid_report())
        inspector = PhotoInspector(model=model, storage=storage)
        photos = [store_photo(storage) for _ in range(MAX_IMAGES_INSPECTED + 4)]

        inspection = await inspector.inspect(photos)

        assert inspection.images_inspected == MAX_IMAGES_INSPECTED
        assert model.images_sent == MAX_IMAGES_INSPECTED

    async def test_damage_photographs_survive_the_cap(self, storage: LocalFileStorage) -> None:
        # When the cap truncates the set, the images most likely to matter
        # must be the ones that get sent.
        model = RecordingVisionModel(valid_report())
        inspector = PhotoInspector(model=model, storage=storage)
        photos = [store_photo(storage) for _ in range(MAX_IMAGES_INSPECTED)]
        photos.append(store_photo(storage, kind=PhotoKind.DAMAGE))

        inspection = await inspector.inspect(photos)

        assert inspection.images_inspected == MAX_IMAGES_INSPECTED

    async def test_a_missing_file_is_skipped_not_fatal(self, storage: LocalFileStorage) -> None:
        model = RecordingVisionModel(valid_report())
        inspector = PhotoInspector(model=model, storage=storage)
        present = store_photo(storage)
        missing = AnalysisPhoto(
            analysis_id=uuid.uuid7(),
            kind=PhotoKind.EXTERIOR,
            storage_key="analysis/does-not-exist.jpg",
            content_type="image/jpeg",
            size_bytes=1,
            original_filename="gone.jpg",
        )

        inspection = await inspector.inspect([present, missing])

        assert inspection.images_inspected == 1

    async def test_a_corrupt_file_is_skipped(self, storage: LocalFileStorage) -> None:
        model = RecordingVisionModel(valid_report())
        inspector = PhotoInspector(model=model, storage=storage)
        corrupt = store_photo(storage, payload=b"not an image at all")

        inspection = await inspector.inspect([corrupt])

        assert not inspection.happened


class TestVisionGuardrails:
    async def test_a_provider_outage_yields_no_findings(self, storage: LocalFileStorage) -> None:
        inspector = PhotoInspector(model=FailingVisionModel(), storage=storage)

        inspection = await inspector.inspect([store_photo(storage)])

        assert not inspection.happened
        assert inspection.findings == ()

    async def test_malformed_json_yields_no_findings(self, storage: LocalFileStorage) -> None:
        inspector = PhotoInspector(model=RecordingVisionModel("bu bir json değil"), storage=storage)

        inspection = await inspector.inspect([store_photo(storage)])

        assert not inspection.happened

    async def test_an_out_of_range_adjustment_discards_the_whole_report(
        self, storage: LocalFileStorage
    ) -> None:
        # A model that ignores the stated bounds forfeits its say entirely;
        # clamping would reward it with partial influence.
        inspector = PhotoInspector(
            model=RecordingVisionModel(valid_report(score_adjustment=-90)),
            storage=storage,
        )

        inspection = await inspector.inspect([store_photo(storage)])

        assert not inspection.happened

    async def test_too_many_findings_discards_the_report(self, storage: LocalFileStorage) -> None:
        finding = {
            "category": "damage",
            "severity": "warning",
            "title": "Çizik",
            "detail": "Detay.",
        }
        inspector = PhotoInspector(
            model=RecordingVisionModel(valid_report(findings=[finding] * 20)),
            storage=storage,
        )

        inspection = await inspector.inspect([store_photo(storage)])

        assert not inspection.happened

    async def test_the_adjustment_bound_is_accepted_at_its_edge(
        self, storage: LocalFileStorage
    ) -> None:
        inspector = PhotoInspector(
            model=RecordingVisionModel(valid_report(score_adjustment=-MAX_VISION_SCORE_ADJUSTMENT)),
            storage=storage,
        )

        inspection = await inspector.inspect([store_photo(storage)])

        assert inspection.score_adjustment == -MAX_VISION_SCORE_ADJUSTMENT


class TestEngineIntegration:
    def _evidence(self, photos: list[AnalysisPhoto]) -> EvidenceSummary:
        return EvidenceSummary(
            photo_count=len(photos),
            photo_kinds=frozenset(photo.kind for photo in photos),
            photos=tuple(photos),
        )

    async def test_visual_findings_reach_the_report(
        self, storage: LocalFileStorage, sample_vehicle: Any
    ) -> None:
        model = RecordingVisionModel(valid_report())
        engine = LLMEnrichedEngine(
            RuleBasedEngine(),
            model,
            PhotoInspector(model=model, storage=storage),
        )
        evidence = self._evidence([store_photo(storage)])

        result = await engine.evaluate(sample_vehicle, evidence)

        titles = [finding.title for finding in result.findings]
        assert "Ön tamponda çizik" in titles

    async def test_a_failed_inspection_still_produces_a_report(
        self, storage: LocalFileStorage, sample_vehicle: Any
    ) -> None:
        # The whole point of the fallback: a report from the data the user
        # typed is still worth having.
        engine = LLMEnrichedEngine(
            RuleBasedEngine(),
            FailingVisionModel(),
            PhotoInspector(model=FailingVisionModel(), storage=storage),
        )
        evidence = self._evidence([store_photo(storage)])

        result = await engine.evaluate(sample_vehicle, evidence)

        assert 0 <= result.trust_score <= 100
        assert result.findings
        assert result.summary

    async def test_the_score_stays_within_bounds_after_a_visual_penalty(
        self, storage: LocalFileStorage, weak_vehicle: Any
    ) -> None:
        model = RecordingVisionModel(valid_report(score_adjustment=-MAX_VISION_SCORE_ADJUSTMENT))
        engine = LLMEnrichedEngine(
            RuleBasedEngine(),
            model,
            PhotoInspector(model=model, storage=storage),
        )
        evidence = self._evidence([store_photo(storage)])

        result = await engine.evaluate(weak_vehicle, evidence)

        assert 0 <= result.trust_score <= 100
