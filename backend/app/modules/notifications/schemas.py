"""Notification Pydantic schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.shared.enums import NotificationStatus


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    recipient_user_id: uuid.UUID
    rule_type: str
    title: str
    body: str
    target_type: str | None
    target_id: uuid.UUID | None
    dedup_key: str
    status: NotificationStatus
    created_at: datetime
    updated_at: datetime


class NotificationStatusUpdate(BaseModel):
    status: NotificationStatus

    def validate_transition(self) -> None:
        """Only read/resolved/silenced are valid target states."""
        allowed = {
            NotificationStatus.read,
            NotificationStatus.resolved,
            NotificationStatus.silenced,
        }
        if self.status not in allowed:
            from app.shared.exceptions import AppException

            raise AppException(
                detail="Estado no válido. Usa 'read', 'resolved' o 'silenced'.",
                code="INVALID_NOTIFICATION_STATUS",
                status_code=422,
            )
