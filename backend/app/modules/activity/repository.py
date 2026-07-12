"""Data-access layer for task history.

``TaskHistory`` is tenant-scoped directly via ``organization_id``
(``TenantMixin``), so queries filter on it without needing a join to
``Task``/``Project``.
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.activity.models import TaskHistory
from app.shared.pagination import PaginationParams, paginate

# Whitelist for ``?sort=`` on the history listings. ``created_at`` (desc) is
# the default order — activity-history.md, "ordenado por changed_at
# descendente por defecto".
SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "created_at": TaskHistory.created_at,
    "field": TaskHistory.field,
}


class ActivityRepository:
    """Async repository encapsulating task-history reads."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_task(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[TaskHistory], int]:
        """Return ``(rows, total)`` — a task's history, newest first by default."""

        stmt = select(TaskHistory).where(
            TaskHistory.task_id == task_id,
            TaskHistory.organization_id == organization_id,
        )

        if pagination is not None and pagination.requested:
            return await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)

        stmt = stmt.order_by(TaskHistory.created_at.desc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return rows, len(rows)

    async def list_for_actor(
        self,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
        *,
        on_date: date | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[TaskHistory], int]:
        """Return ``(rows, total)`` — changes an actor caused, newest first by default.

        ``on_date`` restricts to a single calendar day (``[day, day+1)``,
        UTC); ``date_from``/``date_to`` restrict to an inclusive range.
        """

        stmt = select(TaskHistory).where(
            TaskHistory.actor_id == actor_id,
            TaskHistory.organization_id == organization_id,
        )
        if on_date is not None:
            start = datetime(on_date.year, on_date.month, on_date.day)
            stmt = stmt.where(
                TaskHistory.created_at >= start,
                TaskHistory.created_at < start + timedelta(days=1),
            )
        if date_from is not None:
            stmt = stmt.where(
                TaskHistory.created_at
                >= datetime(date_from.year, date_from.month, date_from.day)
            )
        if date_to is not None:
            stmt = stmt.where(
                TaskHistory.created_at
                < datetime(date_to.year, date_to.month, date_to.day) + timedelta(days=1)
            )

        if pagination is not None and pagination.requested:
            return await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)

        stmt = stmt.order_by(TaskHistory.created_at.desc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return rows, len(rows)

    async def last_activity_by_actor(
        self, organization_id: uuid.UUID
    ) -> dict[uuid.UUID, datetime]:
        """Return ``{actor_id: most_recent_created_at}`` for the organization.

        ``actor_id IS NULL`` (system changes) is excluded — feeds the
        dashboard's ``work_gap`` "no_recent_activity" detection alongside
        ``time_logs.repository.last_activity_by_user``.
        """

        result = await self.db.execute(
            select(TaskHistory.actor_id, func.max(TaskHistory.created_at))
            .where(
                TaskHistory.organization_id == organization_id,
                TaskHistory.actor_id.isnot(None),
            )
            .group_by(TaskHistory.actor_id)
        )
        return {row[0]: row[1] for row in result.all()}
