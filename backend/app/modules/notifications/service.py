"""Notification service — business logic for in-app notifications."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import NotificationStatusUpdate
from app.shared.enums import NotificationStatus
from app.shared.exceptions import AppException


class NotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = NotificationRepository(db)

    async def list_notifications(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        status_filter: NotificationStatus | None,
    ) -> list[Notification]:
        return await self.repo.list_for_user(org_id, user_id, status_filter)

    async def unread_count(self, org_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return await self.repo.count_active(org_id, user_id)

    async def update_status(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        notification_id: uuid.UUID,
        data: NotificationStatusUpdate,
    ) -> Notification:
        data.validate_transition()
        notification = await self.repo.get(org_id, notification_id, user_id)
        if notification is None:
            raise AppException(
                detail="Notificación no encontrada.",
                code="NOTIFICATION_NOT_FOUND",
                status_code=404,
            )
        return await self.repo.update_status(notification, data.status)
