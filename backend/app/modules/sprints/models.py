"""Sprint ORM model.

A sprint groups tasks within a single project for time-boxed delivery
(Scrum). Sprints are tenant-scoped transitively through their project.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import PkMixin, SoftDeleteMixin, TimestampMixin


class Sprint(PkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A time-boxed iteration owned by a project."""

    __tablename__ = "sprints"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Free-form lifecycle value ('active' | 'closed'); validated at the service
    # layer rather than constrained by a database enum.
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False
    )
