"""Data-access layer for the work-calendar module.

Only this layer executes SQL for calendar resolution; ``WorkCalendarResolver``
and ``WorkCalendarService`` depend on it (project convention: "el service
NUNCA toca SQLAlchemy directamente").
"""

import uuid
from decimal import Decimal

from sqlalchemy import Integer, cast, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import settings
from app.modules.projects.models import Project


class WorkCalendarRepository:
    """Resolves the root project's OWN calendar override via a recursive CTE."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def root_override(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> tuple[Decimal | None, list[int] | None] | None:
        """Return the root project's own ``(hours, days)`` override, or ``None``.

        ``None`` overall means ``project_id`` does not exist, is inactive, or
        belongs to another organization — it NEVER crosses ``organization_id``
        (design.md D5). A non-``None`` tuple is whatever the ROOT project
        stores directly: ``(None, None)`` when the root has no override
        configured (design.md, "Data Flow").

        Ascends via ``parent_project_id`` in a SINGLE recursive CTE (base
        term = ``project_id`` itself; recursive term = its parent), bounded
        by ``settings.PROJECT_HIERARCHY_MAX_DEPTH`` — same guard as
        ``ProjectRepository.subtree_height``/``ancestor_ids`` — so a
        pre-existing corrupted cycle can never make this query recurse
        without bound.
        """

        base = select(
            Project.working_hours_per_day,
            Project.working_days,
            Project.parent_project_id,
            cast(literal(0), Integer).label("depth"),
        ).where(
            Project.id == project_id,
            Project.organization_id == organization_id,
            Project.is_active.is_(True),
        )
        ancestors_cte = base.cte(name="work_calendar_ancestors", recursive=True)
        parent = aliased(Project)
        recursive_step = (
            select(
                parent.working_hours_per_day,
                parent.working_days,
                parent.parent_project_id,
                (ancestors_cte.c.depth + 1).label("depth"),
            )
            .join(parent, parent.id == ancestors_cte.c.parent_project_id)
            .where(
                parent.organization_id == organization_id,
                parent.is_active.is_(True),
                ancestors_cte.c.depth < settings.PROJECT_HIERARCHY_MAX_DEPTH,
            )
        )
        ancestors_cte = ancestors_cte.union_all(recursive_step)

        result = await self.db.execute(
            select(
                ancestors_cte.c.working_hours_per_day, ancestors_cte.c.working_days
            )
            .where(ancestors_cte.c.parent_project_id.is_(None))
            .order_by(ancestors_cte.c.depth.desc())
            .limit(1)
        )
        row = result.first()
        if row is None:
            return None
        return row.working_hours_per_day, row.working_days
