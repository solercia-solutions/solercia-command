"""Data-access layer for sprints.

Sprints are scoped to an organization transitively through their project.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.projects.models import Project
from app.modules.sprints.models import Sprint
from app.modules.tasks.models import Task
from app.shared.pagination import PaginationParams, paginate

# Whitelist for ``?sort=`` on ``GET /projects/{id}/sprints``. First entry is
# the default order when pagination is requested without an explicit ``sort``.
SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "created_at": Sprint.created_at,
    "name": Sprint.name,
    "status": Sprint.status,
    "start_date": Sprint.start_date,
}


class SprintRepository:
    """Async repository encapsulating sprint persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_project(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[Sprint], int]:
        """Return ``(sprints, total)`` — active sprints of a project."""

        stmt = select(Sprint).join(Project, Project.id == Sprint.project_id).where(
            Sprint.project_id == project_id,
            Project.organization_id == organization_id,
            Sprint.is_active.is_(True),
        )

        if pagination is not None and pagination.requested:
            return await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)

        stmt = stmt.order_by(Sprint.created_at.desc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return rows, len(rows)

    async def get(
        self, organization_id: uuid.UUID, sprint_id: uuid.UUID
    ) -> Sprint | None:
        """Return a single active sprint scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(Sprint)
            .join(Project, Project.id == Sprint.project_id)
            .where(
                Sprint.id == sprint_id,
                Project.organization_id == organization_id,
                Sprint.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_for_project(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        sprint_id: uuid.UUID,
    ) -> Sprint | None:
        """Return a sprint that belongs to a specific project, or ``None``."""

        result = await self.db.execute(
            select(Sprint)
            .join(Project, Project.id == Sprint.project_id)
            .where(
                Sprint.id == sprint_id,
                Sprint.project_id == project_id,
                Project.organization_id == organization_id,
                Sprint.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_tasks_for_sprint(
        self, organization_id: uuid.UUID, sprint_id: uuid.UUID
    ) -> Sequence[Task]:
        """Return the sprint's active tasks, scoped to the organization."""

        result = await self.db.execute(
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Task.sprint_id == sprint_id,
                Project.organization_id == organization_id,
                Task.is_active.is_(True),
            )
        )
        return result.scalars().all()

    async def list_closed_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Sequence[Sprint]:
        """Return closed sprints of a project ordered by ``closed_at`` ascending."""

        result = await self.db.execute(
            select(Sprint)
            .join(Project, Project.id == Sprint.project_id)
            .where(
                Sprint.project_id == project_id,
                Project.organization_id == organization_id,
                Sprint.status == "closed",
                Sprint.is_active.is_(True),
            )
            .order_by(Sprint.closed_at.asc())
        )
        return result.scalars().all()

    async def sum_done_points_for_sprint(
        self, organization_id: uuid.UUID, sprint_id: uuid.UUID
    ) -> int:
        """Return the sum of ``estimation_points`` for completed tasks in the sprint.

        A task is "done" when its ``completed_at`` is set — this is stamped by
        the task service whenever the task enters the methodology's terminal status.
        Tasks without a point estimate contribute 0.
        """

        result = await self.db.execute(
            select(func.coalesce(func.sum(Task.estimation_points), 0))
            .join(Project, Project.id == Task.project_id)
            .where(
                Task.sprint_id == sprint_id,
                Project.organization_id == organization_id,
                Task.completed_at.isnot(None),
                Task.is_active.is_(True),
            )
        )
        return int(result.scalar_one() or 0)

    async def count_and_move_incomplete_tasks(
        self,
        organization_id: uuid.UUID,
        sprint_id: uuid.UUID,
        target_sprint_id: uuid.UUID | None,
    ) -> int:
        """Move incomplete tasks out of the sprint and return how many were moved.

        Incomplete means ``completed_at IS NULL``. Tasks are moved to
        ``target_sprint_id`` (another sprint) or ``NULL`` (backlog) depending on
        the argument. The sprint was already validated to belong to the
        organization, so the bulk UPDATE does not need a project join.
        """

        # Count with org scoping via project join to be safe.
        count_result = await self.db.execute(
            select(func.count())
            .select_from(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Task.sprint_id == sprint_id,
                Project.organization_id == organization_id,
                Task.completed_at.is_(None),
                Task.is_active.is_(True),
            )
        )
        count = int(count_result.scalar_one() or 0)

        if count > 0:
            await self.db.execute(
                update(Task)
                .where(
                    Task.sprint_id == sprint_id,
                    Task.completed_at.is_(None),
                    Task.is_active.is_(True),
                )
                .values(sprint_id=target_sprint_id)
            )

        return count

    async def count_backlog_points_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> int:
        """Return the sum of ``estimation_points`` for backlog tasks that are not done.

        Backlog = active tasks with no sprint (``sprint_id IS NULL``) and not yet
        completed (``completed_at IS NULL``).
        """

        result = await self.db.execute(
            select(func.coalesce(func.sum(Task.estimation_points), 0))
            .join(Project, Project.id == Task.project_id)
            .where(
                Task.project_id == project_id,
                Project.organization_id == organization_id,
                Task.sprint_id.is_(None),
                Task.completed_at.is_(None),
                Task.is_active.is_(True),
            )
        )
        return int(result.scalar_one() or 0)

    async def create(self, sprint: Sprint) -> Sprint:
        """Persist a new sprint and return the refreshed instance."""

        self.db.add(sprint)
        await self.db.commit()
        await self.db.refresh(sprint)
        return sprint

    async def save(self, sprint: Sprint) -> Sprint:
        """Commit pending changes on an attached sprint and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(sprint)
        return sprint
