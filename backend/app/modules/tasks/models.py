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
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
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

    if TYPE_CHECKING:
        # Transient attribute attached by TaskService for response
        # serialization only; never persisted (no mapped_column/column).
        assignee_name: str | None
