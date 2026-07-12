"""Notifications router — in-app notifications for current user."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_membership
from app.modules.notifications.schemas import NotificationRead, NotificationStatusUpdate
from app.modules.notifications.service import NotificationService
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import NotificationStatus
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=dict)
async def list_notifications(
    status: NotificationStatus | None = Query(default=None),
    pagination: PaginationParams = Depends(pagination_params),
    db: AsyncSession = Depends(get_db),
    membership: OrganizationMember = Depends(get_current_membership),
) -> dict:
    """List notifications for the current user. Defaults to active only.

    Supports opt-in pagination (``page``/``size``/``sort``/``order``); without
    those params the full collection is returned unchanged.
    """
    service = NotificationService(db)
    notifications, total = await service.list_notifications(
        membership.organization_id, membership.user_id, status, pagination
    )
    return {
        "data": [NotificationRead.model_validate(n).model_dump() for n in notifications],
        "message": "Notificaciones obtenidas.",
        "meta": build_list_meta(pagination, total),
    }


@router.get("/unread-count", response_model=dict)
async def unread_count(
    db: AsyncSession = Depends(get_db),
    membership: OrganizationMember = Depends(get_current_membership),
) -> dict:
    """Return the count of active (unread) notifications for the current user."""
    service = NotificationService(db)
    count = await service.unread_count(membership.organization_id, membership.user_id)
    return {"data": {"count": count}, "message": "Conteo de notificaciones no leídas."}


@router.patch("/{notification_id}", response_model=dict)
async def update_notification_status(
    notification_id: uuid.UUID,
    data: NotificationStatusUpdate,
    db: AsyncSession = Depends(get_db),
    membership: OrganizationMember = Depends(get_current_membership),
) -> dict:
    """Update the status of a notification (read, resolved, silenced)."""
    service = NotificationService(db)
    notification = await service.update_status(
        membership.organization_id, membership.user_id, notification_id, data
    )
    await db.commit()
    return {
        "data": NotificationRead.model_validate(notification).model_dump(),
        "message": "Estado de notificación actualizado.",
        "meta": {},
    }
