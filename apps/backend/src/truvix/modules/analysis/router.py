"""HTTP endpoints for the analysis workflow."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Form, UploadFile, status
from fastapi.responses import FileResponse

from truvix.modules.analysis.dependencies import AnalysisServiceDep
from truvix.modules.analysis.models import PhotoKind
from truvix.modules.analysis.schemas import (
    AnalysisPhotoResponse,
    AnalysisResponse,
    AnalysisSummaryResponse,
)
from truvix.modules.auth.dependencies import CurrentUserDep
from truvix.shared.errors import PROBLEM_CONTENT_TYPE
from truvix.shared.pagination import Page, PageParamsDep

router = APIRouter(prefix="/analyses", tags=["analyses"])

_PROBLEM: dict[str, Any] = {"content": {PROBLEM_CONTENT_TYPE: {}}}
_UNAUTHORISED: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"description": "Access token missing or invalid.", **_PROBLEM},
}
_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    **_UNAUTHORISED,
    status.HTTP_404_NOT_FOUND: {
        "description": "No such analysis in this account.",
        **_PROBLEM,
    },
}
_STATE_CONFLICT: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    status.HTTP_409_CONFLICT: {
        "description": "The analysis is not in a state that allows this action.",
        **_PROBLEM,
    },
}
_QUOTA: dict[int | str, dict[str, Any]] = {
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "description": "The account has spent today's analysis allowance.",
        **_PROBLEM,
    },
}


@router.post(
    "",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open an analysis",
    description="Creates a pending analysis for one of the caller's vehicles.",
    responses=_NOT_FOUND,
)
async def create_analysis(
    vehicle_id: Annotated[uuid.UUID, Form()],
    current_user: CurrentUserDep,
    service: AnalysisServiceDep,
) -> AnalysisResponse:
    """Open a new analysis run."""
    analysis = await service.create(owner_id=current_user.id, vehicle_id=vehicle_id)
    return AnalysisResponse.from_analysis(analysis)


@router.get(
    "",
    response_model=Page[AnalysisSummaryResponse],
    summary="List analyses",
    description="Returns a page of the caller's analyses, newest first.",
    responses=_UNAUTHORISED,
)
async def list_analyses(
    current_user: CurrentUserDep,
    service: AnalysisServiceDep,
    params: PageParamsDep,
) -> Page[AnalysisSummaryResponse]:
    """List the caller's analyses."""
    return await service.list(owner_id=current_user.id, params=params)


@router.get(
    "/{analysis_id}",
    response_model=AnalysisResponse,
    summary="Read an analysis",
    description="Returns one analysis with its report when completed.",
    responses=_NOT_FOUND,
)
async def read_analysis(
    analysis_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: AnalysisServiceDep,
) -> AnalysisResponse:
    """Return one of the caller's analyses."""
    analysis = await service.get(owner_id=current_user.id, analysis_id=analysis_id)
    return AnalysisResponse.from_analysis(analysis)


@router.post(
    "/{analysis_id}/photos",
    response_model=AnalysisPhotoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach evidence",
    description=(
        "Uploads a photo or PDF to a pending analysis. The file's type is "
        "determined from its bytes; the declared content type is ignored."
    ),
    responses={
        **_STATE_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Unsupported file type or size.",
            **_PROBLEM,
        },
    },
)
async def upload_photo(
    analysis_id: uuid.UUID,
    file: UploadFile,
    current_user: CurrentUserDep,
    service: AnalysisServiceDep,
    kind: Annotated[PhotoKind, Form()] = PhotoKind.OTHER,
) -> AnalysisPhotoResponse:
    """Attach a photo or document to an analysis."""
    photo = await service.attach_photo(
        owner_id=current_user.id,
        analysis_id=analysis_id,
        stream=file.file,
        kind=kind,
        original_filename=file.filename,
    )
    return AnalysisPhotoResponse.from_photo(photo)


@router.get(
    "/{analysis_id}/photos/{photo_id}",
    summary="Download evidence",
    description="Streams a previously uploaded photo or document.",
    response_class=FileResponse,
    responses=_NOT_FOUND,
)
async def download_photo(
    analysis_id: uuid.UUID,
    photo_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: AnalysisServiceDep,
) -> FileResponse:
    """Stream one attached file back to its owner."""
    photo, path = await service.open_photo(
        owner_id=current_user.id, analysis_id=analysis_id, photo_id=photo_id
    )
    return FileResponse(path, media_type=photo.content_type)


@router.post(
    "/{analysis_id}/start",
    response_model=AnalysisResponse,
    summary="Run an analysis",
    description=(
        "Starts a pending analysis and returns the finished report. Each run "
        "counts against the account's daily allowance."
    ),
    responses={**_STATE_CONFLICT, **_QUOTA},
)
async def start_analysis(
    analysis_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: AnalysisServiceDep,
) -> AnalysisResponse:
    """Run one of the caller's pending analyses."""
    analysis = await service.start(
        owner_id=current_user.id,
        analysis_id=analysis_id,
        tier=current_user.subscription_tier,
    )
    return AnalysisResponse.from_analysis(analysis)
