"""Reminder and ReminderRule ORM models.

Both are strictly personal resources scoped by ``user_id`` (owner) in addition
to ``organization_id`` (``TenantMixin``): not even an org admin may see or
manage another user's reminders (specs/reminders/spec.md, "Aislamiento
multi-tenant y personal"). ``Reminder`` mirrors the mixin set of
``AlertRule``/``TaskTimeLog`` (Pk+Timestamp+SoftDelete+Audit+Tenant).
``ReminderRule.params`` is a JSON dict (default ``{"lead_days": 3}``) instead
of a dedicated ``lead_days`` column so a future ``rule_type`` (e.g.
``license_expiring``) can carry different params with zero migration
(design.md, "ReminderRule con lead_days DENTRO de params JSON").
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    AuditMixin,
    PkMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from app.shared.enums import ReminderStatus


class Reminder(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """A one-shot manual reminder owned by a single user."""

    __tablename__ = "reminders"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReminderStatus] = mapped_column(
        SAEnum(ReminderStatus, name="reminder_status", native_enum=False, length=20),
        default=ReminderStatus.scheduled,
        nullable=False,
        index=True,
    )
    fired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ReminderRule(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """A per-user configurable rule that produces automatic reminders (e.g. task_due_soon)."""

    __tablename__ = "reminder_rules"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True
    )
    rule_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    params: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"lead_days": 3}, nullable=False
    )
