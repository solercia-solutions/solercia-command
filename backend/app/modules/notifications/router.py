"""Notifications router — in-app notifications for current user."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership
from app.modules.notifications.schemas import (
    NotificationPreferenceUpdate,
    NotificationRead,
    NotificationStatusUpdate,
)
from app.modules.notifications.service import NotificationPreferenceService, NotificationService
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import NotificationStatus
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(prefix="/notifications", tags=["notifications"])

# Deliberately NO shared prefix with `router` above: the contract is a flat
# GET/PUT /notification-preferences (specs/email-notifications/spec.md),
# not nested under /notifications (design.md D6 correction over the
# proposal's suggested /notifications/preferences).
preferences_router = APIRouter(tags=["notifications"])


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


@router.get("/{notification_id}/deliveries", response_model=dict)
async def list_notification_deliveries(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    membership: OrganizationMember = Depends(get_current_membership),
) -> dict:
    """Audit a notification's per-channel delivery attempts.

    Restricted to ``admin``/``manager`` of the notification's organization
    (change 12-notification-hub, design.md D6) — even the notification's own
    owner gets ``403`` if not also a supervisor.
    """
    service = NotificationService(db)
    result = await service.list_deliveries(
        membership.organization_id, notification_id, membership.role
    )
    return {
        "data": result.model_dump(),
        "message": "Entregas de la notificación obtenidas.",
        "meta": {},
    }


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


@preferences_router.get("/notification-preferences", response_model=dict)
async def get_notification_preference(
    db: AsyncSession = Depends(get_db),
    membership: OrganizationMember = Depends(get_current_membership),
) -> dict:
    """Return the caller's own digest preference (or virtual defaults)."""
    service = NotificationPreferenceService(db)
    preference = await service.get_preference(membership.organization_id, membership.user_id)
    return {
        "data": preference.model_dump(),
        "message": "Preferencia de notificaciones obtenida.",
        "meta": {},
    }


@preferences_router.put("/notification-preferences", response_model=dict)
async def update_notification_preference(
    data: NotificationPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
) -> dict:
    """Create or update the caller's own digest preference."""
    service = NotificationPreferenceService(db)
    preference = await service.update_preference(
        membership.organization_id, membership.user_id, data, actor_id=actor_id
    )
    await db.commit()
    return {
        "data": preference.model_dump(),
        "message": "Preferencia de notificaciones actualizada.",
        "meta": {},
    }
