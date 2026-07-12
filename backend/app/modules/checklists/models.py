"""TaskChecklist and ChecklistItem ORM models.

A ``TaskChecklist`` breaks down the "how" of executing a task without
creating formal subtasks; each has ordered ``ChecklistItem`` rows that can be
marked done. Both are tenant-scoped directly via ``TenantMixin`` (design.md,
"Correcciones de gate (2026-07-11)" #4 — direct ``organization_id`` column,
same precedent as ``TaskComment``/``Attachment``).
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    AuditMixin,
    PkMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)


class TaskChecklist(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """A named checklist attached to a task."""

    __tablename__ = "task_checklists"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    # Ordering hint among a task's checklists. Mapped to a non-reserved
    # column name, same pattern as Task.order -> "task_order".
    order: Mapped[int] = mapped_column(
        "checklist_order", Integer, default=0, nullable=False
    )


class ChecklistItem(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """A single markable item within a ``TaskChecklist``."""

    __tablename__ = "checklist_items"

    checklist_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("task_checklists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Ordering hint among a checklist's items.
    order: Mapped[int] = mapped_column(
        "item_order", Integer, default=0, nullable=False
    )
