"""Data-access layer for tasks and assignable members.

Tasks are scoped to an organization transitively through their project, so
every read joins ``Task`` to ``Project`` and filters by ``organization_id``.
"""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.organizations.models import OrganizationMember
from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from app.modules.users.models import User
from app.shared.enums import MemberRole, Priority
from app.shared.pagination import PaginationParams, paginate

# Whitelist for ``?sort=`` on ``GET /projects/{id}/tasks``. The first entry is
# the default order when pagination is requested without an explicit ``sort``.
# ``assignee_name`` is deliberately excluded: it's a Python-side computed
# field (see ``TaskService._to_read``), not an ORM column in this statement.
SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "order": Task.order,
    "title": Task.title,
    "status": Task.status,
    "priority": Task.priority,
    "due_date": Task.due_date,
    "created_at": Task.created_at,
}


class TaskRepository:
    """Async repository encapsulating task persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_project(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        sprint_id: uuid.UUID | None = None,
        status: str | None = None,
        assignee_id: uuid.UUID | None = None,
        parent_task_id: uuid.UUID | None = None,
        task_type: str | None = None,
        label_ids: Sequence[uuid.UUID] | None = None,
        priority: Priority | None = None,
        due_from: date | None = None,
        due_to: date | None = None,
        q: str | None = None,
        subtasks_only: bool = False,
        top_level_only: bool = False,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[Task], int]:
        """Return active tasks of a project, filtered and ordered for a board.

        Returns ``(rows, total)``. When ``pagination`` is ``None`` or the
        caller didn't opt in (see :attr:`PaginationParams.requested`), ``rows``
        is the full filtered collection (byte-compatible with the pre-pagination
        behavior) and ``total`` is simply ``len(rows)``.

        ``label_ids`` (one or more) matches ANY of the given labels (OR
        semantics, deduplicated via ``.distinct()``); ``due_from``/``due_to``
        filter on the DATE portion of ``due_date`` (a task with no
        ``due_date`` never matches a range filter, change 10-busqueda-global
        design.md "Decisión 5").
        """

        stmt = (
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Task.project_id == project_id,
                Project.organization_id == organization_id,
                Task.is_active.is_(True),
            )
        )
        if sprint_id is not None:
            stmt = stmt.where(Task.sprint_id == sprint_id)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if assignee_id is not None:
            stmt = stmt.where(Task.assignee_id == assignee_id)
        if parent_task_id is not None:
            stmt = stmt.where(Task.parent_task_id == parent_task_id)
        if task_type is not None:
            stmt = stmt.where(Task.task_type == task_type)
        if subtasks_only:
            stmt = stmt.where(Task.parent_task_id.isnot(None))
        if top_level_only:
            stmt = stmt.where(Task.parent_task_id.is_(None))
        if label_ids:
            # Deferred import: `tasks` never depends on `labels` at module
            # level (mirrors the `boards` deferred-import pattern, design.md
            # C4) — `labels` is the module that depends on `tasks`.
            from app.modules.labels.models import TaskLabel

            stmt = (
                stmt.join(TaskLabel, TaskLabel.task_id == Task.id)
                .where(TaskLabel.label_id.in_(label_ids))
                .distinct()
            )
        if priority is not None:
            stmt = stmt.where(Task.priority == priority)
        if due_from is not None:
            stmt = stmt.where(func.date(Task.due_date) >= due_from)
        if due_to is not None:
            stmt = stmt.where(func.date(Task.due_date) <= due_to)
        if q is not None:
            pattern = f"%{q}%"
            stmt = stmt.where(Task.title.ilike(pattern) | Task.description.ilike(pattern))

        if pagination is not None and pagination.requested:
            return await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)

        stmt = stmt.order_by(Task.order.asc(), Task.created_at.asc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return rows, len(rows)

    async def get_by_ids(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        ids: Sequence[uuid.UUID],
    ) -> Sequence[Task]:
        """Return active tasks matching ``ids``, scoped to org/project.

        Used by the assignee-filter context-parent rule (change
        32-jerarquia-subtareas, D2): resolves the foreign parents of matched
        subtasks. Never crosses tenant/project boundaries, same as every
        other read in this repository. Returns ``[]`` without querying when
        ``ids`` is empty.
        """

        if not ids:
            return []

        result = await self.db.execute(
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Task.id.in_(ids),
                Task.project_id == project_id,
                Project.organization_id == organization_id,
                Task.is_active.is_(True),
            )
        )
        return result.scalars().all()

    async def list_for_org(
        self, organization_id: uuid.UUID
    ) -> Sequence[Task]:
        """Return every active task across the organization's projects."""

        result = await self.db.execute(
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Project.organization_id == organization_id,
                Project.is_active.is_(True),
                Task.is_active.is_(True),
            )
        )
        return result.scalars().all()

    async def get(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> Task | None:
        """Return a single active task scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Task.id == task_id,
                Project.organization_id == organization_id,
                Task.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_external_key(
        self,
        organization_id: uuid.UUID,
        source: str,
        external_key: str,
    ) -> Task | None:
        """Return an active external anchor within one organization."""

        result = await self.db.execute(
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Task.source == source,
                Task.external_key == external_key,
                Project.organization_id == organization_id,
                Project.is_active.is_(True),
                Task.is_active.is_(True),
            )
            .order_by(Task.created_at.asc(), Task.id.asc())
            .limit(1)
        )
        return result.scalars().first()

    async def get_by_project_and_number(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        task_number: int,
    ) -> Task | None:
        """Return the active task identified by its sequential project number."""

        result = await self.db.execute(
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Task.project_id == project_id,
                Task.task_number == task_number,
                Project.organization_id == organization_id,
                Task.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def allocate_task_number(self, project_id: uuid.UUID) -> int:
        """Atomically increment the project task counter and return the new value.

        Uses ``UPDATE ... RETURNING`` inside the current transaction so no two
        concurrent requests receive the same task_number for the same project.
        The surrounding ``commit()`` in :meth:`create` seals both operations
        (counter increment + task row INSERT) into a single atomic transaction.
        """

        result = await self.db.execute(
            text(
                "UPDATE projects "
                "SET task_counter = task_counter + 1 "
                "WHERE id = :project_id "
                "RETURNING task_counter"
            ),
            {"project_id": str(project_id)},
        )
        return result.scalar_one()

    async def create(self, task: Task) -> Task:
        """Persist a new task and return the refreshed instance."""

        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def save(self, task: Task) -> Task:
        """Flush pending changes on an attached task and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_subtask_counts(
        self, task_id: uuid.UUID, done_status: str
    ) -> tuple[int, int]:
        """Return ``(total, done)`` subtask counts for ``task_id``."""

        total_result = await self.db.execute(
            select(func.count()).select_from(Task).where(
                Task.parent_task_id == task_id,
                Task.is_active.is_(True),
            )
        )
        total = total_result.scalar_one() or 0

        done_result = await self.db.execute(
            select(func.count()).select_from(Task).where(
                Task.parent_task_id == task_id,
                Task.status == done_status,
                Task.is_active.is_(True),
            )
        )
        done = done_result.scalar_one() or 0
        return total, done

    async def list_org_members(
        self, organization_id: uuid.UUID
    ) -> Sequence[tuple[User, MemberRole]]:
        """Return ``(User, role)`` pairs for the organization's active members."""

        result = await self.db.execute(
            select(User, OrganizationMember.role)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(
                OrganizationMember.organization_id == organization_id,
                User.is_active.is_(True),
            )
            .order_by(User.full_name.asc())  # type: ignore[attr-defined]
        )
        return list(result.tuples().all())

    async def reassign_order_for_container(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        ordered_task_ids: Sequence[uuid.UUID],
    ) -> None:
        """Set ``task.order`` to each id's index within ``ordered_task_ids``.

        Scoped to ``organization_id``/``project_id``/``is_active`` so a
        malformed id from another tenant or project is silently excluded
        rather than reassigned. Does NOT commit — the caller
        (``TaskService.reorder_tasks``) closes the transaction with its own
        ``repo.save()`` so the sprint move and the reindex land atomically
        (design.md D1, "1 transacción").
        """

        if not ordered_task_ids:
            return

        result = await self.db.execute(
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Task.id.in_(ordered_task_ids),
                Task.project_id == project_id,
                Project.organization_id == organization_id,
                Task.is_active.is_(True),
            )
        )
        tasks_by_id = {task.id: task for task in result.scalars().all()}
        for index, task_id in enumerate(ordered_task_ids):
            task = tasks_by_id.get(task_id)
            if task is not None:
                task.order = index

    async def is_org_member(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Return whether the user belongs to the organization."""

        result = await self.db.execute(
            select(OrganizationMember.id).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None
