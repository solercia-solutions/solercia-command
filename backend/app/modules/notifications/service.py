"""Notification service — business logic for in-app notifications."""
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification
from app.modules.notifications.repository import (
    NotificationPreferenceRepository,
    NotificationRepository,
)
from app.modules.notifications.schemas import (
    NotificationDeliveriesRead,
    NotificationDeliveryRead,
    NotificationPreferenceRead,
    NotificationPreferenceUpdate,
    NotificationStatusUpdate,
)
from app.shared.enums import DigestFrequency, MemberRole, NotificationStatus
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams

# Defaults applied when a user has no NotificationPreference row yet (D7,
# "opt-in, no sorprender") — mirrored by the ORM column defaults so a freshly
# upserted row and the virtual default read the same values.
_DEFAULT_DIGEST_HOUR = 8

# Roles allowed to audit another notification's per-channel delivery
# attempts (change 12-notification-hub, design.md D6) — SIN excepción de
# dueño: it is an operational audit endpoint whose payload exposes
# recipient_email/last_error, the owner already has GET /notifications.
_SUPERVISOR_ROLES = (MemberRole.admin, MemberRole.manager)


class NotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = NotificationRepository(db)

    async def list_notifications(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        status_filter: NotificationStatus | None,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[Notification], int]:
        return await self.repo.list_for_user(
            org_id, user_id, status_filter, pagination
        )

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

    async def list_deliveries(
        self,
        org_id: uuid.UUID,
        notification_id: uuid.UUID,
        requester_role: MemberRole,
    ) -> NotificationDeliveriesRead:
        """Audit a notification's per-channel delivery attempts (change
        12-notification-hub, design.md D6). ``admin``/``manager`` ONLY, no
        owner exemption; ``404`` if the notification is not in ``org_id``.
        """

        if requester_role not in _SUPERVISOR_ROLES:
            raise AppException(
                detail="No tienes permisos para consultar las entregas de "
                "esta notificación.",
                code="notification_deliveries_forbidden",
                status_code=403,
            )

        notification = await self.repo.get_for_org(org_id, notification_id)
        if notification is None:
            raise AppException(
                detail="Notificación no encontrada.",
                code="NOTIFICATION_NOT_FOUND",
                status_code=404,
            )

        deliveries = await self.repo.list_deliveries(notification.id)
        # D6, "opción (b)": emailed_at set but NO immediate row -> the
        # digest covered it with an aggregated (not 1:1) delivery row.
        digested = notification.emailed_at is not None and not deliveries
        return NotificationDeliveriesRead(
            deliveries=[
                NotificationDeliveryRead.model_validate(row) for row in deliveries
            ],
            digested=digested,
        )


class NotificationPreferenceService:
    """Orchestrates the caller's own digest preference (change 08, Fase C)."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = NotificationPreferenceRepository(db)

    async def get_preference(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> NotificationPreferenceRead:
        """Return the persisted preference, or sensible virtual defaults (D7)."""
        pref = await self.repo.get_or_none(org_id, user_id)
        if pref is None:
            return NotificationPreferenceRead(
                frequency=DigestFrequency.none.value,
                hour=_DEFAULT_DIGEST_HOUR,
                weekday=None,
            )
        return NotificationPreferenceRead(
            frequency=pref.digest_frequency.value,
            hour=pref.digest_hour,
            weekday=pref.digest_weekday,
        )

    async def update_preference(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        data: NotificationPreferenceUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> NotificationPreferenceRead:
        """Validate (Pydantic already did) and upsert the caller's preference."""
        pref = await self.repo.upsert(
            org_id,
            user_id,
            frequency=DigestFrequency(data.frequency),
            hour=data.hour,
            weekday=data.weekday,
            actor_id=actor_id,
        )
        return NotificationPreferenceRead(
            frequency=pref.digest_frequency.value,
            hour=pref.digest_hour,
            weekday=pref.digest_weekday,
        )
