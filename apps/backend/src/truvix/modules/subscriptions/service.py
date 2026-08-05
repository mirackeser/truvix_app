"""Subscription business logic: redeeming transactions and deriving the tier."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truvix.modules.subscriptions.models import Entitlement, EntitlementStatus
from truvix.modules.subscriptions.verification import (
    AppStoreVerifier,
    VerifiedTransaction,
    decode_unverified,
)
from truvix.modules.users.models import SubscriptionTier, User
from truvix.shared.errors import ConflictError, NotFoundError, ServiceUnavailableError
from truvix.shared.logging import get_logger

_logger = get_logger(__name__)


class SubscriptionService:
    """Redeems verified purchases and keeps the account's tier in step."""

    def __init__(self, session: AsyncSession, verifier: AppStoreVerifier | None = None) -> None:
        """Initialise the service.

        Args:
            session: The session whose transaction this service participates in.
            verifier: Checks that a transaction really came from Apple, for us.
                Optional because reading what an account already holds needs no
                verifier, and a deployment that cannot take payments must still
                be able to answer what plan somebody is on.
        """
        self._session = session
        self._verifier = verifier

    @property
    def _checked_verifier(self) -> AppStoreVerifier:
        """The verifier, or a refusal if this deployment has none.

        Raises:
            ServiceUnavailableError: When no verifier is configured. Accepting
                an unverified transaction would hand out premium for free, so
                refusing is the only safe answer.
        """
        if self._verifier is None:
            raise ServiceUnavailableError("Abonelikler bu kurulumda yapılandırılmamış.")
        return self._verifier

    async def redeem(self, *, user_id: uuid.UUID, signed_payload: str) -> Entitlement:
        """Verify a signed transaction and grant what it entitles.

        Args:
            user_id: The account presenting the transaction.
            signed_payload: The JWS as StoreKit produced it.

        Returns:
            The entitlement, created or refreshed.

        Raises:
            DomainValidationError: If the transaction does not verify.
            ConflictError: If the subscription already belongs to another
                account.
            NotFoundError: If the account no longer exists.
        """
        transaction = self._checked_verifier.verify(signed_payload)

        existing = await self._session.scalar(
            select(Entitlement).where(
                Entitlement.original_transaction_id == transaction.original_transaction_id
            )
        )

        if existing is not None and existing.user_id != user_id:
            # One purchase, one account. Without this, a subscription could be
            # shared by passing the same signed transaction around.
            _logger.warning(
                "entitlement_claimed_by_another_account",
                original_transaction_id=transaction.original_transaction_id,
            )
            raise ConflictError(
                "Bu abonelik başka bir hesaba tanımlı. Aboneliğin bağlı olduğu hesapla giriş yap."
            )

        entitlement = existing or Entitlement(
            user_id=user_id,
            original_transaction_id=transaction.original_transaction_id,
            product_id=transaction.product_id,
            latest_transaction_id=transaction.transaction_id,
            status=transaction.status,
            environment=transaction.environment,
            purchased_at=transaction.purchased_at,
        )
        self._apply(entitlement, transaction)

        if existing is None:
            self._session.add(entitlement)
        await self._session.flush()

        await self.refresh_tier(user_id)
        _logger.info(
            "entitlement_redeemed",
            user_id=str(user_id),
            product_id=transaction.product_id,
            status=transaction.status.value,
        )
        return entitlement

    async def apply_store_notification(self, signed_payload: str) -> Entitlement | None:
        """Apply a change the App Store reported for a subscription we hold.

        Renewals, cancellations and refunds arrive this way rather than through
        the app, because the app may not be running when they happen. A
        notification for a subscription nobody has redeemed is ignored: there is
        no account to attach it to, and inventing one would be worse.

        Args:
            signed_payload: The ``signedPayload`` envelope Apple posts.

        Returns:
            The updated entitlement, or ``None`` when it is not one of ours.

        Raises:
            DomainValidationError: If the envelope or the transaction inside it
                does not verify. Nothing about this request is trusted before
                that: the endpoint is unauthenticated, so the signature is the
                only thing separating Apple from anyone who knows the URL.
        """
        verifier = self._checked_verifier
        transaction = verifier.verify(verifier.verify_notification(signed_payload))

        entitlement = await self._session.scalar(
            select(Entitlement).where(
                Entitlement.original_transaction_id == transaction.original_transaction_id
            )
        )
        if entitlement is None:
            _logger.info(
                "store_notification_ignored",
                original_transaction_id=transaction.original_transaction_id,
                unverified=decode_unverified(signed_payload).get("notificationType"),
            )
            return None

        self._apply(entitlement, transaction)
        await self._session.flush()
        await self.refresh_tier(entitlement.user_id)

        _logger.info(
            "entitlement_updated_from_store",
            user_id=str(entitlement.user_id),
            status=transaction.status.value,
        )
        return entitlement

    async def refresh_tier(self, user_id: uuid.UUID) -> SubscriptionTier:
        """Recompute the account's tier from its entitlements.

        The tier on the account is a cache of this answer, kept because nearly
        every request needs it and none of them should join three tables to get
        it. Recomputing rather than toggling means a lapsed subscription cannot
        leave an account premium because one code path forgot to unset it.

        Args:
            user_id: The account to recompute.

        Returns:
            The tier the account now holds.

        Raises:
            NotFoundError: If the account no longer exists.
        """
        user = await self._session.get(User, user_id)
        if user is None:
            raise NotFoundError.for_resource("User", user_id)

        entitlements = (
            await self._session.scalars(select(Entitlement).where(Entitlement.user_id == user_id))
        ).all()

        now = datetime.now(UTC)
        tier = (
            SubscriptionTier.PREMIUM
            if any(entitlement.is_current(now=now) for entitlement in entitlements)
            else SubscriptionTier.FREE
        )

        if user.subscription_tier is not tier:
            _logger.info(
                "subscription_tier_changed",
                user_id=str(user_id),
                to=tier.value,
            )
            user.subscription_tier = tier
            await self._session.flush()
        return tier

    async def entitlements_for(self, user_id: uuid.UUID) -> list[Entitlement]:
        """List an account's entitlements, newest purchase first.

        Args:
            user_id: The account to read.
        """
        result = await self._session.scalars(
            select(Entitlement)
            .where(Entitlement.user_id == user_id)
            .order_by(Entitlement.purchased_at.desc())
        )
        return list(result.all())

    @staticmethod
    def _apply(entitlement: Entitlement, transaction: VerifiedTransaction) -> None:
        """Copy a verified transaction onto an entitlement.

        Older transactions are ignored rather than applied. Apple may deliver
        notifications out of order, and letting a stale one overwrite a newer
        state would revive an expired subscription or cancel a live one.
        """
        if transaction.purchased_at < entitlement.purchased_at:
            _logger.info(
                "stale_transaction_ignored",
                original_transaction_id=transaction.original_transaction_id,
            )
            return

        entitlement.product_id = transaction.product_id
        entitlement.latest_transaction_id = transaction.transaction_id
        entitlement.environment = transaction.environment
        entitlement.purchased_at = transaction.purchased_at
        entitlement.expires_at = transaction.expires_at
        entitlement.revoked_at = transaction.revoked_at
        entitlement.status = (
            EntitlementStatus.REVOKED if transaction.revoked_at is not None else transaction.status
        )
