"""Notification repository — database access for Notification model."""
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.email.outbox import enqueue_immediate_email
from app.modules.notifications.models import Notification, NotificationPreference
from app.realtime.publisher import buffer_notification
from app.shared.enums import DigestFrequency, NotificationStatus
from app.shared.pagination import PaginationParams, paginate

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

        Also buffers it for realtime push (``buffer_notification``) and, if
        urgent, enqueues it for immediate email delivery in the SAME
        transaction (``enqueue_immediate_email`` — change 08, design.md D2):
        the evaluator and comment mentions both call this method directly
        (the service layer has no ``create()`` of its own), so this is the
        ONE place that needs to know about either channel. The realtime push
        happens later, when the transaction owner drains the buffer with
        ``flush_pending(db)`` right after ``commit()``; the email is drained
        later still by the ``email_dispatch`` job (D3) — neither channel
        blocks or can fail this write.
        """
        notification = Notification(**kwargs)
        self.db.add(notification)
        await self.db.flush()
        await self.db.refresh(notification)
        buffer_notification(self.db, notification)
        await enqueue_immediate_email(self.db, notification)
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
