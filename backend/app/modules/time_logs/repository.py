"""Data-access layer for time logs.

``TaskTimeLog`` is tenant-scoped directly via ``organization_id``
(``TenantMixin``), so most queries filter on it without needing a join to
``Task``/``Project`` (unlike ``tasks``/``sprints``, which are scoped
transitively).
"""

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.time_logs.models import TaskTimeLog
from app.shared.pagination import PaginationParams, paginate

# Whitelist for ``?sort=`` on the time-log listings. The first entry is the
# default order when pagination is requested without an explicit ``sort``.
SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "date": TaskTimeLog.work_date,
    "created_at": TaskTimeLog.created_at,
    "hours": TaskTimeLog.hours,
}


class TimeLogRepository:
    """Async repository encapsulating time-log persistence and aggregation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_task(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[TaskTimeLog], int]:
        """Return ``(entries, total)`` — active entries of a task."""

        stmt = select(TaskTimeLog).where(
            TaskTimeLog.task_id == task_id,
            TaskTimeLog.organization_id == organization_id,
            TaskTimeLog.is_active.is_(True),
        )

        if pagination is not None and pagination.requested:
            return await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)

        stmt = stmt.order_by(TaskTimeLog.work_date.desc(), TaskTimeLog.created_at.desc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return rows, len(rows)

    async def list_for_user(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[TaskTimeLog], int]:
        """Return ``(entries, total)`` — active entries of a user, optionally date-bounded."""

        stmt = select(TaskTimeLog).where(
            TaskTimeLog.user_id == user_id,
            TaskTimeLog.organization_id == organization_id,
            TaskTimeLog.is_active.is_(True),
        )
        if date_from is not None:
            stmt = stmt.where(TaskTimeLog.work_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(TaskTimeLog.work_date <= date_to)

        if pagination is not None and pagination.requested:
            return await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)

        stmt = stmt.order_by(TaskTimeLog.work_date.desc(), TaskTimeLog.created_at.desc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return rows, len(rows)

    async def get(
        self, organization_id: uuid.UUID, log_id: uuid.UUID
    ) -> TaskTimeLog | None:
        """Return a single active entry scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(TaskTimeLog).where(
                TaskTimeLog.id == log_id,
                TaskTimeLog.organization_id == organization_id,
                TaskTimeLog.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, log: TaskTimeLog) -> TaskTimeLog:
        """Persist a new entry and return the refreshed instance."""

        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def save(self, log: TaskTimeLog) -> TaskTimeLog:
        """Flush pending changes on an attached entry and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def daily_summary(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[tuple[date, Decimal]]:
        """Return ``[(work_date, total_hours), ...]`` for a user, one row per day."""

        stmt = (
            select(TaskTimeLog.work_date, func.sum(TaskTimeLog.hours))
            .where(
                TaskTimeLog.user_id == user_id,
                TaskTimeLog.organization_id == organization_id,
                TaskTimeLog.is_active.is_(True),
            )
            .group_by(TaskTimeLog.work_date)
            .order_by(TaskTimeLog.work_date.asc())
        )
        if date_from is not None:
            stmt = stmt.where(TaskTimeLog.work_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(TaskTimeLog.work_date <= date_to)

        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def weekly_summary(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[tuple[date, Decimal]]:
        """Return ``[(week_start, total_hours), ...]`` — ISO week (Monday-anchored) sums."""

        week_start = cast(func.date_trunc("week", TaskTimeLog.work_date), Date)
        stmt = (
            select(week_start.label("week_start"), func.sum(TaskTimeLog.hours))
            .where(
                TaskTimeLog.user_id == user_id,
                TaskTimeLog.organization_id == organization_id,
                TaskTimeLog.is_active.is_(True),
            )
            .group_by(week_start)
            .order_by(week_start.asc())
        )
        if date_from is not None:
            stmt = stmt.where(TaskTimeLog.work_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(TaskTimeLog.work_date <= date_to)

        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def hours_by_user(
        self,
        organization_id: uuid.UUID,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[uuid.UUID, Decimal]:
        """Return ``{user_id: total_hours}`` for the organization within a date window.

        One ``GROUP BY`` query — feeds the dashboard's ``work_gap`` block
        (design.md Interfaces/Contracts, ``hours_by_user``).
        """

        stmt = (
            select(TaskTimeLog.user_id, func.sum(TaskTimeLog.hours))
            .where(
                TaskTimeLog.organization_id == organization_id,
                TaskTimeLog.is_active.is_(True),
            )
            .group_by(TaskTimeLog.user_id)
        )
        if date_from is not None:
            stmt = stmt.where(TaskTimeLog.work_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(TaskTimeLog.work_date <= date_to)

        result = await self.db.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def last_activity_by_user(
        self,
        organization_id: uuid.UUID,
    ) -> dict[uuid.UUID, date]:
        """Return ``{user_id: most_recent_work_date}`` for the organization.

        Feeds the dashboard's ``work_gap`` "no_recent_activity" detection
        alongside ``activity.repository.last_activity_by_actor``.
        """

        result = await self.db.execute(
            select(TaskTimeLog.user_id, func.max(TaskTimeLog.work_date))
            .where(
                TaskTimeLog.organization_id == organization_id,
                TaskTimeLog.is_active.is_(True),
            )
            .group_by(TaskTimeLog.user_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def task_ids_with_recent_entries(
        self, organization_id: uuid.UUID, since: date
    ) -> set[uuid.UUID]:
        """Return the distinct ``task_id``s with a log dated ``since`` or later.

        Feeds the dashboard's ``work_gap`` "tasks_with_activity" count
        alongside ``activity.repository.task_ids_with_recent_entries``.
        """

        result = await self.db.execute(
            select(TaskTimeLog.task_id)
            .distinct()
            .where(
                TaskTimeLog.organization_id == organization_id,
                TaskTimeLog.is_active.is_(True),
                TaskTimeLog.work_date >= since,
            )
        )
        return set(result.scalars().all())
