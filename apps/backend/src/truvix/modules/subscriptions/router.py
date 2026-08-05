"""HTTP endpoints for subscriptions."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Self

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field

from truvix.modules.auth.dependencies import CurrentUserDep
from truvix.modules.subscriptions.models import (
    Entitlement,
    EntitlementStatus,
    StoreEnvironment,
)
from truvix.modules.subscriptions.service import SubscriptionService
from truvix.modules.subscriptions.verification import AppStoreVerifier
from truvix.modules.users.models import SubscriptionTier
from truvix.shared.dependencies import SessionDep, SettingsDep
from truvix.shared.errors import PROBLEM_CONTENT_TYPE, ServiceUnavailableError
from truvix.shared.logging import get_logger
from truvix.shared.ratelimit import enforce_store_notification_rate_limit
from truvix.shared.schemas import StrictRequest

_logger = get_logger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

_PROBLEM: dict[str, Any] = {"content": {PROBLEM_CONTENT_TYPE: {}}}

# StoreKit payloads are compact; anything far larger is not one, and refusing
# it early keeps an oversized body away from the certificate parser.
_MAX_SIGNED_PAYLOAD_LENGTH = 32_768


class RedeemRequest(StrictRequest):
    """A signed transaction the app received from StoreKit."""

    signed_transaction: Annotated[str, Field(min_length=1, max_length=_MAX_SIGNED_PAYLOAD_LENGTH)]


class StoreNotificationRequest(StrictRequest):
    """The envelope Apple posts to the server notification URL."""

    signed_payload: Annotated[
        str, Field(min_length=1, max_length=_MAX_SIGNED_PAYLOAD_LENGTH, alias="signedPayload")
    ]


class EntitlementResponse(BaseModel):
    """One subscription the account holds."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: str
    status: EntitlementStatus
    environment: StoreEnvironment
    purchased_at: datetime
    expires_at: datetime | None
    is_current: bool

    @classmethod
    def from_entitlement(cls, entitlement: Entitlement) -> Self:
        """Build the response from a persisted entitlement."""
        return cls(
            id=entitlement.id,
            product_id=entitlement.product_id,
            status=entitlement.status,
            environment=entitlement.environment,
            purchased_at=entitlement.purchased_at,
            expires_at=entitlement.expires_at,
            is_current=entitlement.is_current(),
        )


class SubscriptionStateResponse(BaseModel):
    """The account's plan and what it holds."""

    tier: SubscriptionTier
    is_premium: bool
    entitlements: list[EntitlementResponse]


def get_verifier(settings: SettingsDep) -> AppStoreVerifier:
    """Build the transaction verifier for this deployment.

    Raises:
        ServiceUnavailableError: When the deployment is not configured to
            verify purchases. Refusing is the only safe answer — accepting an
            unverified transaction would hand out premium for free.
    """
    configuration = settings.subscription
    if configuration.bundle_id is None:
        raise ServiceUnavailableError("Abonelikler bu kurulumda yapılandırılmamış.")

    roots = _load_roots(configuration.apple_root_certificate_dir)
    if not roots:
        _logger.error(
            "apple_roots_missing", directory=str(configuration.apple_root_certificate_dir)
        )
        raise ServiceUnavailableError("Abonelik doğrulaması şu anda kullanılamıyor.")

    return AppStoreVerifier(
        root_certificates=roots,
        expected_bundle_id=configuration.bundle_id,
        allow_sandbox=configuration.allow_sandbox,
    )


def _load_roots(directory: Path) -> list[bytes]:
    """Read every certificate shipped in the roots directory."""
    if not directory.is_dir():
        return []
    return [
        path.read_bytes()
        for path in sorted(directory.iterdir())
        if path.suffix.lower() in {".cer", ".der", ".pem", ".crt"}
    ]


VerifierDep = Annotated[AppStoreVerifier, Depends(get_verifier)]


def get_subscription_service(session: SessionDep, verifier: VerifierDep) -> SubscriptionService:
    """Provide the subscription service for the current request."""
    return SubscriptionService(session, verifier)


SubscriptionServiceDep = Annotated[SubscriptionService, Depends(get_subscription_service)]


@router.get(
    "",
    response_model=SubscriptionStateResponse,
    summary="Subscription state",
    description="Returns the caller's plan and the entitlements behind it.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Access token missing or invalid.",
            **_PROBLEM,
        }
    },
)
async def read_state(
    current_user: CurrentUserDep,
    session: SessionDep,
) -> SubscriptionStateResponse:
    """Return the caller's subscription state.

    Deliberately does not require a configured verifier: an account still has a
    plan on a deployment that cannot take payments, and the app needs to render
    it.
    """
    service = SubscriptionService(session)
    entitlements = await service.entitlements_for(current_user.id)
    return SubscriptionStateResponse(
        tier=current_user.subscription_tier,
        is_premium=current_user.is_premium,
        entitlements=[
            EntitlementResponse.from_entitlement(entitlement) for entitlement in entitlements
        ],
    )


@router.post(
    "/notifications",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_store_notification_rate_limit)],
    summary="App Store server notification",
    description=(
        "Receives subscription changes from the App Store: renewals, "
        "cancellations, refunds and expiries. Unauthenticated by design — Apple "
        "cannot hold a token — so the payload's signature is what authenticates "
        "the caller."
    ),
    responses={
        status.HTTP_204_NO_CONTENT: {"description": "Notification accepted."},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The notification did not verify.",
            **_PROBLEM,
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Subscriptions are not configured on this deployment.",
            **_PROBLEM,
        },
    },
)
async def receive_store_notification(
    payload: StoreNotificationRequest,
    service: SubscriptionServiceDep,
) -> None:
    """Apply a subscription change the App Store reported.

    A refund or cancellation only reaches us this way: the app may not be
    running when it happens, so without this endpoint a refunded customer would
    keep premium until their paid term ran out.

    A notification about a subscription nobody has redeemed here is accepted and
    ignored rather than refused, so that Apple does not retry something that
    will never succeed.
    """
    await service.apply_store_notification(payload.signed_payload)


@router.post(
    "/redeem",
    response_model=SubscriptionStateResponse,
    summary="Redeem a purchase",
    description=(
        "Verifies a signed StoreKit transaction and grants what it entitles. "
        "The transaction's signature chain must terminate at an Apple root and "
        "name this application."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Access token missing or invalid.",
            **_PROBLEM,
        },
        status.HTTP_409_CONFLICT: {
            "description": "The subscription belongs to another account.",
            **_PROBLEM,
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The transaction did not verify.",
            **_PROBLEM,
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Subscriptions are not configured on this deployment.",
            **_PROBLEM,
        },
    },
)
async def redeem(
    payload: RedeemRequest,
    current_user: CurrentUserDep,
    service: SubscriptionServiceDep,
    session: SessionDep,
) -> SubscriptionStateResponse:
    """Redeem a signed StoreKit transaction."""
    await service.redeem(user_id=current_user.id, signed_payload=payload.signed_transaction)

    entitlements = await service.entitlements_for(current_user.id)
    # Re-read the account: redeeming may have changed its tier, and returning
    # the value the request arrived with would show the old plan.
    await session.refresh(current_user)
    return SubscriptionStateResponse(
        tier=current_user.subscription_tier,
        is_premium=current_user.is_premium,
        entitlements=[
            EntitlementResponse.from_entitlement(entitlement) for entitlement in entitlements
        ],
    )
