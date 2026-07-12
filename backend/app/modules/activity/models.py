"""TaskHistory ORM model.

An append-only changelog row: one field changed by one actor at one moment.
No ``SoftDeleteMixin``/``AuditMixin`` — the row IS the audit record (its own
``actor_id``/``actor_type`` play that role), same precedent as
``Notification``. Tenant-scoped directly via ``TenantMixin``. Not
``TimestampMixin``: this row has no meaningful "updated_at" (append-only,
never mutated after insert) — only a creation moment, aliased by the API as
``changed_at`` (see ``activity.schemas.TaskHistoryResponse``).

Note: this model is registered in Batch A (T01's shared migration creates
both ``task_time_logs`` and ``task_history`` in one revision) so
``alembic check`` stays a no-diff against the ORM baseline
(``tests/test_migrations_baseline.py``) immediately after that migration
lands. The rest of the ``activity`` module (recorder/schemas/repository/
service/router) is built in Batch B per tasks.md T09-T19.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import PkMixin, TenantMixin


class TaskHistory(PkMixin, TenantMixin, Base):
    """A single field change on a task, attributed to a user or the system."""

    __tablename__ = "task_history"
    __table_args__ = (
        Index("ix_task_history_task_id_created_at", "task_id", "created_at"),
        Index("ix_task_history_actor_id_created_at", "actor_id", "created_at"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    # NULL when the change was made by the system (e.g. sprint close).
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    field: Mapped[str] = mapped_column(String(60), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Python-side ``default`` (NOT just ``server_default``): Postgres' ``now()``
    # is fixed for the lifetime of a SQL transaction, not per-statement. Every
    # request in this codebase's test suite shares ONE outer transaction
    # (SAVEPOINT-nested), so several history rows inserted across separate
    # requests within the same test would otherwise get the IDENTICAL
    # ``created_at`` and make ``ORDER BY created_at DESC`` non-deterministic
    # for ties. ``datetime.now(UTC)`` is evaluated in Python at INSERT time
    # (once per row, real wall-clock), giving a genuinely increasing
    # timestamp per change. ``server_default`` stays as a DB-level fallback
    # for rows inserted outside the ORM.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
