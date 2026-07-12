"""TaskTimeLog ORM model.

Registers hours a user actually worked on a task ("trabajo realizado"), the
source of truth the executive dashboard's ``work_gap`` block compares against
each task's ``estimation_hours``. Tenant-scoped directly via ``TenantMixin``
(established convention for change 05 — same precedent as
``TaskComment``/``TaskChecklist``). No ``UniqueConstraint``: a user may log
several entries the same day (even on the same task); the aggregation sums
them (time-logs.md, "Agregación diaria y semanal").
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    AuditMixin,
    PkMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)


class TaskTimeLog(
    PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base
):
    """An entry of hours a user logged against a task on a given day."""

    __tablename__ = "task_time_logs"
    __table_args__ = (
        Index("ix_task_time_logs_user_id_work_date", "user_id", "work_date"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )
    # Column name kept distinct from the API's ``date`` alias (see
    # ``time_logs.schemas.TimeLogResponse``) — "date" collides with the Python
    # builtin and with SQL reserved-word conventions used elsewhere in this
    # codebase (mirrors ``Task.order`` -> ``task_order``).
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
