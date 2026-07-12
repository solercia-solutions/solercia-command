"""Data-access layer for task dependency edges (``task_dependencies``)."""

import uuid
from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.task_links.models import TaskDependency
from app.modules.tasks.models import Task
from app.shared.pagination import PaginationParams, paginate

# Whitelist for ``?sort=`` on ``GET /tasks/{id}/dependencies``. First entry is
# the default order when pagination is requested without an explicit ``sort``.
SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "created_at": TaskDependency.created_at,
}


class TaskDependencyRepository:
    """Async repository encapsulating dependency-edge persistence and reads."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_task(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[TaskDependency], int]:
        """Return ``(edges, total)`` — active edges touching ``task_id``, either direction."""

        stmt = select(TaskDependency).where(
            or_(
                TaskDependency.blocker_task_id == task_id,
                TaskDependency.blocked_task_id == task_id,
            ),
            TaskDependency.organization_id == organization_id,
            TaskDependency.is_active.is_(True),
        )
        if pagination is not None and pagination.requested:
            return await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)

        stmt = stmt.order_by(TaskDependency.created_at.asc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return rows, len(rows)

    async def get_for_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID, dependency_id: uuid.UUID
    ) -> TaskDependency | None:
        """Return a single active edge touching ``task_id``, scoped to the org."""

        result = await self.db.execute(
            select(TaskDependency).where(
                TaskDependency.id == dependency_id,
                TaskDependency.organization_id == organization_id,
                TaskDependency.is_active.is_(True),
                or_(
                    TaskDependency.blocker_task_id == task_id,
                    TaskDependency.blocked_task_id == task_id,
                ),
            )
        )
        return result.scalar_one_or_none()

    async def get_edge_any_state(
        self, blocker_task_id: uuid.UUID, blocked_task_id: uuid.UUID
    ) -> TaskDependency | None:
        """Return the edge row for this exact ordered pair, active or not.

        The ``UniqueConstraint(blocker_task_id, blocked_task_id)`` is not
        filtered by ``is_active`` — re-linking a pair that was previously
        unlinked (soft-deleted) must reactivate the existing row rather than
        insert a duplicate (which would violate the constraint).
        """

        result = await self.db.execute(
            select(TaskDependency).where(
                TaskDependency.blocker_task_id == blocker_task_id,
                TaskDependency.blocked_task_id == blocked_task_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_active_edges_for_project(
        self, project_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Return every active ``(blocker_task_id, blocked_task_id)`` edge of a project.

        A single query — the caller builds the adjacency graph and runs the
        cycle-detection DFS in Python (design.md, "Detección de ciclos por
        DFS en el servicio"). Scoped via a join on the blocker's
        ``project_id`` — both ends of an edge are always validated to share
        the same project at creation time, so this join alone captures every
        edge of the project.
        """

        result = await self.db.execute(
            select(TaskDependency.blocker_task_id, TaskDependency.blocked_task_id)
            .join(Task, Task.id == TaskDependency.blocker_task_id)
            .where(Task.project_id == project_id, TaskDependency.is_active.is_(True))
        )
        return [(row.blocker_task_id, row.blocked_task_id) for row in result]

    async def get_incomplete_blockers(
        self, task_id: uuid.UUID
    ) -> Sequence[tuple[uuid.UUID, str]]:
        """Return ``(task_id, title)`` for every active, incomplete blocker of ``task_id``.

        "Incomplete" = ``completed_at IS NULL`` (design.md gate correction
        #3 — the spec's "completado o cancelado" clause is not implementable
        today, no ``cancelled`` state exists in the codebase; cancellation
        stays a traced deviation). One query, bounded to a single task.
        """

        result = await self.db.execute(
            select(Task.id, Task.title)
            .join(TaskDependency, TaskDependency.blocker_task_id == Task.id)
            .where(
                TaskDependency.blocked_task_id == task_id,
                TaskDependency.is_active.is_(True),
                Task.completed_at.is_(None),
                Task.is_active.is_(True),
            )
        )
        return [(row.id, row.title) for row in result]

    async def create(self, dependency: TaskDependency) -> TaskDependency:
        """Persist a new edge and return the refreshed instance."""

        self.db.add(dependency)
        await self.db.commit()
        await self.db.refresh(dependency)
        return dependency

    async def save(self, dependency: TaskDependency) -> TaskDependency:
        """Flush pending changes on an attached edge and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(dependency)
        return dependency
