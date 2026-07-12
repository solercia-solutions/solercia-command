"""Board and BoardColumn ORM models.

A ``Board`` is the persisted representation of a project's board, seeded from
the project's methodology Strategy (``strategy.default_columns()``) at
project-creation time. Each ``BoardColumn`` carries the ``status_key`` a
``Task`` adopts when it enters that column — the single source of truth for
``allowed_statuses()`` once a board has been configured (see
``app.methodology.board_aware``). Both models are tenant-scoped transitively
through their project, the same pattern already used by ``Task``.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    AuditMixin,
    PkMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class Board(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    """A project's board. Exactly one active board exists per project."""

    __tablename__ = "boards"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    if TYPE_CHECKING:
        # Transient attribute attached by BoardRepository for response
        # serialization only; never persisted (no mapped_column/column).
        # Mirrors the pattern of Task.assignee_name / Project.methodology_info.
        columns: list["BoardColumn"]


class BoardColumn(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    """A column on a board — the status a task adopts when it enters it."""

    __tablename__ = "board_columns"
    __table_args__ = (
        UniqueConstraint("board_id", "status_key", name="uq_board_column_status_key"),
    )

    board_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("boards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Visible label; mutable via the rename endpoint.
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # The status a Task adopts when it enters this column. Immutable once
    # created — renaming ``name`` never changes ``status_key`` (see design.md
    # D5). For methodology-seeded columns this equals the strategy's column
    # name verbatim (backward-compatible with existing Task.status values).
    status_key: Mapped[str] = mapped_column(String(60), nullable=False)
    # Ordering hint within the board. Mapped to a non-reserved column name,
    # same pattern as Task.order -> "task_order".
    order: Mapped[int] = mapped_column(
        "column_order", Integer, default=0, nullable=False
    )
    # Nullable = no WIP limit.
    wip_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
