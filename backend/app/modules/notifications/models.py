"""Notification ORM models — in-app notification per user + per-user digest
preference (``NotificationPreference``, change 08 Fase C, D1/D7)."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import AuditMixin, PkMixin, TenantMixin, TimestampMixin
from app.shared.enums import DigestFrequency, NotificationStatus


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


class NotificationPreference(PkMixin, TimestampMixin, AuditMixin, TenantMixin, Base):
    """A user's email digest cadence — one row per ``(organization_id, user_id)``.

    Deliberately NO ``SoftDeleteMixin``: this is a singleton preference per
    user, upserted in place (``NotificationPreferenceRepository.upsert``),
    never soft-deleted (design.md D6/D7).
    """

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", name="uq_notification_preferences_org_user"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    digest_frequency: Mapped[DigestFrequency] = mapped_column(
        SAEnum(DigestFrequency, name="digest_frequency", native_enum=False, length=10),
        default=DigestFrequency.none,
        nullable=False,
    )
    digest_hour: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    digest_weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_digest_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
