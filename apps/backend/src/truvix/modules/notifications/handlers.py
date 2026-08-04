"""Event handlers that turn domain events into notifications.

Handlers run inside the publishing request's transaction, after its work and
before its commit, and always consult the recipient's preferences first: a
switched-off category produces nothing rather than an unread badge.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from truvix.modules.analysis.models import RiskLevel
from truvix.modules.notifications.models import NotificationCategory
from truvix.modules.notifications.service import NotificationService
from truvix.shared.events import (
    AnalysisCompleted,
    DomainEvent,
    PriceDropped,
    registry,
)
from truvix.shared.formatting import format_number

EVENT_PRICE_DROP = "price_drop"
EVENT_ANALYSIS_COMPLETED = "analysis_completed"
EVENT_RISK_ALERT = "risk_alert"


async def _on_price_dropped(session: AsyncSession, event: DomainEvent) -> None:
    """File a price drop under the opportunities tab."""
    assert isinstance(event, PriceDropped)
    service = NotificationService(session)
    preferences = await service.preferences_for(event.user_id)
    if not preferences.price_changes:
        return

    drop = event.previous_price - event.new_price
    await service.record(
        user_id=event.user_id,
        category=NotificationCategory.OPPORTUNITY,
        event_type=EVENT_PRICE_DROP,
        title="Fiyat düştü!",
        body=(
            f"İzlediğiniz {event.vehicle_name} {format_number(drop)} TL düştü. "
            "Pazarlık için uygun bir zaman olabilir."
        ),
        vehicle_id=event.vehicle_id,
    )


async def _on_analysis_completed(session: AsyncSession, event: DomainEvent) -> None:
    """File a finished report under AI suggestions, and risks when warranted."""
    assert isinstance(event, AnalysisCompleted)
    service = NotificationService(session)
    preferences = await service.preferences_for(event.user_id)

    if preferences.ai_suggestions:
        await service.record(
            user_id=event.user_id,
            category=NotificationCategory.AI_SUGGESTION,
            event_type=EVENT_ANALYSIS_COMPLETED,
            title="Analiz tamamlandı",
            body=(f"{event.vehicle_name} için analiz hazır. Güven skoru: {event.trust_score}/100."),
            vehicle_id=event.vehicle_id,
        )

    if event.risk_level == RiskLevel.HIGH.value and preferences.risk_alerts:
        await service.record(
            user_id=event.user_id,
            category=NotificationCategory.RISK,
            event_type=EVENT_RISK_ALERT,
            title="Risk uyarısı",
            body=(
                f"{event.vehicle_name} yüksek riskli görünüyor "
                f"(güven skoru {event.trust_score}/100). Detayları kontrol edin."
            ),
            vehicle_id=event.vehicle_id,
        )


def register_notification_handlers() -> None:
    """Subscribe the handlers; safe to call more than once."""
    registry.register(PriceDropped, _on_price_dropped)
    registry.register(AnalysisCompleted, _on_analysis_completed)
