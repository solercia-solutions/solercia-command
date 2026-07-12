"""Label and TaskLabel ORM models.

A ``Label`` is a project-scoped tag used to classify and filter tasks.
``TaskLabel`` is the M:N association between a ``Task`` and a ``Label``.
Both are tenant-scoped directly via ``TenantMixin`` (design.md, "Correcciones
de gate (2026-07-11)" #4 — direct ``organization_id`` column, same precedent
as ``TaskComment``/``Attachment``).
"""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    AuditMixin,
    PkMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)


class Label(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """A project-scoped tag. ``name`` is unique among a project's active labels."""

    __tablename__ = "labels"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_labels_project_name"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False)


class TaskLabel(PkMixin, TimestampMixin, Base):
    """M:N link between a ``Task`` and a ``Label``.

    Follows the ``Role``/``UserRole`` association convention (design.md,
    "Decisión: Modelo de datos"): a surrogate ``PkMixin`` id + a
    ``UniqueConstraint``, no ``SoftDeleteMixin`` — unlinking a task/label pair
    removes the row outright (hard delete), it is never soft-deleted itself.
    """

    __tablename__ = "task_labels"
    __table_args__ = (
        UniqueConstraint("task_id", "label_id", name="uq_task_labels_task_label"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("labels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
