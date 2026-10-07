"""``scheduled_sync_runs``: INSERT-ONLY log of every daily_sync run.

One row per (run, organization): a run is recorded once, when it finishes,
with each step's status, counts and error. There is no update nor delete
path, so the table has no soft-delete flags and no ``updated_*`` columns
(same convention as ``organization_theme_versions``). Mirrored by migration
0029 so ``create_all`` (tests) and ``alembic check`` agree.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import PkMixin


class ScheduledSyncRun(PkMixin, Base):
    __tablename__ = "scheduled_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "trigger IN ('scheduled', 'manual')", name="ck_scheduled_sync_runs_trigger"
        ),
        CheckConstraint(
            "status IN ('success', 'partial', 'failed')", name="ck_scheduled_sync_runs_status"
        ),
        Index("ix_scheduled_sync_runs_org_started", "organization_id", "started_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Who pressed «Sincronizar ahora»; ``NULL`` for the scheduler.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    #: Ordered ``[{name, status, counts, detail, error}]``.
    steps: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
