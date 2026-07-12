"""Notification ORM model — in-app notification per user."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import PkMixin, TenantMixin, TimestampMixin
from app.shared.enums import NotificationStatus


class Notification(PkMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "notifications"

    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # Unique key to prevent duplicate alerts: e.g. "task_overdue:{task_id}"
    dedup_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    status: Mapped[NotificationStatus] = mapped_column(
        SAEnum(NotificationStatus, name="notification_status", native_enum=False, length=20),
        default=NotificationStatus.active,
        nullable=False,
        index=True,
    )
    # Set the moment this notification is delivered by email (immediate or
    # digest) — NULL until then. Prevents the digest from re-summarizing a
    # notification already sent, and lets the immediate-send hook mark it
    # atomically in the same transaction that creates the row (D2).
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
