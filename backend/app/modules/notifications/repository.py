"""Notification repository — database access for Notification model."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification
from app.shared.enums import NotificationStatus


class NotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_user(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        status_filter: NotificationStatus | None = None,
    ) -> list[Notification]:
        """Return notifications for a user. Defaults to active only."""
        query = (
            select(Notification)
            .where(
                Notification.organization_id == org_id,
                Notification.recipient_user_id == user_id,
            )
            .order_by(Notification.created_at.desc())
        )
        if status_filter is not None:
            query = query.where(Notification.status == status_filter)
        else:
            query = query.where(Notification.status == NotificationStatus.active)
        result = await self.db.execute(query)
        return list(result.scalars().all())

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
