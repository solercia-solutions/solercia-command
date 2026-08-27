"""Task ORM model.

A task is the unit of work on a project board. Its ``status`` is a free-form
string validated at the service layer against the project methodology's
``allowed_statuses`` (the board columns) instead of a global enum, so the same
table powers every methodology. Tasks are tenant-scoped transitively through
their project.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    AuditMixin,
    PkMixin,
    SoftDeleteMixin,
    TimestampMixin,
)
from app.shared.enums import Priority


class Task(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    """A work item belonging to a project, optionally tied to a sprint."""

    __tablename__ = "tasks"
    __table_args__ = (
        # Trigram GIN indexes backing GET /search (change 10-busqueda-global,
        # design.md "Índices GIN"); accelerate ILIKE '%q%' + similarity().
        Index(
            "ix_tasks_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index(
            "ix_tasks_description_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "gin_trgm_ops"},
        ),
        # External-origin anchor (change 43-tareas-origen-externo). Declared HERE
        # and not only in migration 0025 because the test harness builds the
        # schema with `Base.metadata.create_all` (tests/conftest.py:74-80), same
        # rule as `uq_users_numero_documento` (users/models.py:28-39).
        # The predicates below are BYTE-IDENTICAL to 0025: `alembic check` does
        # NOT compare partial-index WHERE clauses nor CHECK constraints
        # (alembic 1.14.0, ddl/postgresql.py:322-380), so the equivalence is
        # asserted by test_migration_task_external_origin.py, not by the gate.
        CheckConstraint(
            "external_key IS NULL OR source IS NOT NULL",
            name="ck_tasks_external_key_requires_source",
        ),
        # `(source, external_key, project_id)`: same per-project uniqueness as the
        # reverse order, but the leading `(source, external_key)` prefix ALSO
        # serves `get_by_external_key`'s org-wide lookup — which is why this is
        # the only index the anchor needs (design.md D-A).
        # `AND is_active`: a soft-deleted task RELEASES its anchor, so the index
        # covers exactly the rows the seam considers to exist (design.md D-I).
        Index(
            "uq_tasks_source_external_key_project",
            "source",
            "external_key",
            "project_id",
            unique=True,
            postgresql_where=text("source IS NOT NULL AND external_key IS NOT NULL AND is_active"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sprint_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("sprints.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Board column the task currently sits in. Nullable: legacy rows keep
    # working via `status` alone until backfilled, and `custom` boards with
    # zero columns leave every task without one. `status` stays the single
    # field validated against the strategy; `board_column_id` is the runtime
    # source of `status` once a board is configured (see
    # `app.methodology.board_aware` and `app.modules.boards.service`).
    board_column_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("board_columns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Work item kind ('task' | 'bug' | 'story' | 'epic'); free-form string.
    task_type: Mapped[str] = mapped_column(
        String(40), default="task", nullable=False
    )
    # Board column. Validated against the project methodology's allowed statuses
    # at the service layer; intentionally NOT a global enum.
    status: Mapped[str] = mapped_column(String(60), nullable=False)
    priority: Mapped[Priority] = mapped_column(
        SAEnum(Priority, name="task_priority", native_enum=False, length=20),
        default=Priority.medium,
        nullable=False,
    )

    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    estimation_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimation_hours: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )

    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Stamped when the task enters the methodology's "done" column (the last
    # allowed status) and cleared when it leaves it. Drives burndown/performance.
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Ordering hint within a column/backlog. Mapped to a non-reserved column
    # name to stay clear of the SQL ``ORDER`` keyword.
    order: Mapped[int] = mapped_column(
        "task_order", Integer, default=0, nullable=False
    )

    risk_flag: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    risk_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Sequential number scoped to the project (e.g. task #7 of project "SDM"
    # → task_key "SDM-7"). Assigned atomically via UPDATE ... RETURNING on
    # projects.task_counter. Nullable for backward-compat with existing rows.
    task_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Origin system of an imported task (change 43). Free-form string validated at
    # the write layer against `app.modules.tasks.sources.KNOWN_TASK_SOURCES`,
    # deliberately NOT a PG enum (same reason as `connectors.provider`). NULL on
    # every manually created task — there is no `manual` sentinel (D4).
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Opaque key of the task in `source` (e.g. "T-05", "PROJ-123", an Outlook
    # internetMessageId). Length aligned with `intake_items.external_id`, the
    # value change 47 copies verbatim.
    external_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    if TYPE_CHECKING:
        # Transient attribute attached by TaskService for response
        # serialization only; never persisted (no mapped_column/column).
        assignee_name: str | None
