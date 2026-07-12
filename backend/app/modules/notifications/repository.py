"""Notification repository — database access for Notification model."""
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.notifications.models import Notification
from app.shared.enums import NotificationStatus
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
        notification = Notification(**kwargs)
        self.db.add(notification)
        await self.db.flush()
        await self.db.refresh(notification)
        return notification
