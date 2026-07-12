"""Notification repository — database access for Notification model."""
import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.notifications.models import Notification, NotificationPreference
from app.notify.models import NotificationDelivery
from app.notify.ports import DeliveryPolicy
from app.notify.registry import get_channels
from app.shared.enums import DigestFrequency, NotificationStatus
from app.shared.pagination import PaginationParams, paginate

logger = logging.getLogger("solercia.notifications.repository")

# Whitelist for ``?sort=`` on ``GET /notifications``. First entry is the
# default order when pagination is requested without an explicit ``sort``.
SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "created_at": Notification.created_at,
    "title": Notification.title,
    "status": Notification.status,
}


class NotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_user(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        status_filter: NotificationStatus | None = None,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[Notification], int]:
        """Return ``(notifications, total)`` for a user. Defaults to active only."""
        query = select(Notification).where(
            Notification.organization_id == org_id,
            Notification.recipient_user_id == user_id,
        )
        if status_filter is not None:
            query = query.where(Notification.status == status_filter)
        else:
            query = query.where(Notification.status == NotificationStatus.active)

        if pagination is not None and pagination.requested:
            return await paginate(self.db, query, pagination, SORTABLE_FIELDS)

        query = query.order_by(Notification.created_at.desc())
        result = await self.db.execute(query)
        rows = result.scalars().all()
        return rows, len(rows)

    async def count_active(self, org_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """Count active notifications for a user."""
        result = await self.db.execute(
            select(func.count(Notification.id)).where(
                Notification.organization_id == org_id,
                Notification.recipient_user_id == user_id,
                Notification.status == NotificationStatus.active,
            )
        )
        return result.scalar_one() or 0

    async def get(
        self,
        org_id: uuid.UUID,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Notification | None:
        # Scope by recipient too: a notification is private to its owner, so a
        # peer in the same org must not be able to mutate it by guessing the id.
        result = await self.db.execute(
            select(Notification).where(
                Notification.organization_id == org_id,
                Notification.id == notification_id,
                Notification.recipient_user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_org(
        self, org_id: uuid.UUID, notification_id: uuid.UUID
    ) -> Notification | None:
        """Fetch a notification scoped ONLY by organization — no recipient
        filter. Used by the admin/manager delivery-audit endpoint (change
        12-notification-hub, design.md D6): unlike ``get()``, a supervisor
        may audit a notification they do not own.
        """
        result = await self.db.execute(
            select(Notification).where(
                Notification.organization_id == org_id,
                Notification.id == notification_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_deliveries(
        self, notification_id: uuid.UUID
    ) -> Sequence[NotificationDelivery]:
        """Return the immediate (1:1 attributed) delivery rows for a
        notification — a digest's aggregated row is deliberately excluded
        (``notification_id IS NULL`` on that row, design.md D6)."""
        result = await self.db.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification_id
            )
        )
        return result.scalars().all()

    async def update_status(
        self, notification: Notification, status: NotificationStatus
    ) -> Notification:
        notification.status = status
        self.db.add(notification)
        await self.db.flush()
        await self.db.refresh(notification)
        return notification

    async def exists_active(self, org_id: uuid.UUID, dedup_key: str) -> bool:
        """Return True if an active notification with this dedup_key already exists."""
        result = await self.db.execute(
            select(func.count(Notification.id)).where(
                Notification.organization_id == org_id,
                Notification.dedup_key == dedup_key,
                Notification.status == NotificationStatus.active,
            )
        )
        return (result.scalar_one() or 0) > 0

    async def create(self, **kwargs) -> Notification:
        """Persist a notification — the single point where one is born.

        Fans out to EVERY channel registered in the hub (change
        12-notification-hub, design.md D2/R2): the evaluator and comment
        mentions both call this method directly (the service layer has no
        ``create()`` of its own), so this is the ONE place that needs to
        know about the channel registry. A ``durable`` channel's
        ``enqueue(db, n)`` runs in the SAME transaction (e.g. email); a
        ``best_effort`` channel's ``buffer(db, n)`` queues for a later,
        external post-commit flush (e.g. realtime). A channel that raises
        is logged and skipped — it MUST NOT break notification persistence
        NOR any other channel's delivery (gate correction, R2 "aislamiento
        de fallos").
        """
        notification = Notification(**kwargs)
        self.db.add(notification)
        await self.db.flush()
        await self.db.refresh(notification)

        for channel in get_channels():
            try:
                if channel.policy == DeliveryPolicy.durable:
                    await channel.enqueue(self.db, notification)  # type: ignore[attr-defined]
                else:
                    channel.buffer(self.db, notification)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 - one channel's failure must never break create() or the others
                logger.exception(
                    "Canal de entrega %s falló durante el fan-out de la "
                    "notificación %s.",
                    channel.name,
                    notification.id,
                )

        return notification


class NotificationPreferenceRepository:
    """Repository for the caller's own digest preference — a singleton row
    per ``(organization_id, user_id)`` (change 08, Fase C)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_none(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> NotificationPreference | None:
        result = await self.db.execute(
            select(NotificationPreference).where(
                NotificationPreference.organization_id == org_id,
                NotificationPreference.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        frequency: DigestFrequency,
        hour: int,
        weekday: int | None,
        actor_id: uuid.UUID | None = None,
    ) -> NotificationPreference:
        """Create the row if it does not exist yet, otherwise update it in place."""
        existing = await self.get_or_none(org_id, user_id)
        if existing is None:
            existing = NotificationPreference(
                organization_id=org_id,
                user_id=user_id,
                created_by=actor_id,
            )
            self.db.add(existing)

        existing.digest_frequency = frequency
        existing.digest_hour = hour
        existing.digest_weekday = weekday
        existing.updated_by = actor_id
        self.db.add(existing)
        await self.db.flush()
        await self.db.refresh(existing)
        return existing
