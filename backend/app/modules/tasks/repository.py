"""Data-access layer for tasks and assignable members.

Tasks are scoped to an organization transitively through their project, so
every read joins ``Task`` to ``Project`` and filters by ``organization_id``.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import OrganizationMember
from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from app.modules.users.models import User


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
    ) -> Sequence[Task]:
        """Return active tasks of a project, filtered and ordered for a board."""

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

        stmt = stmt.order_by(Task.order.asc(), Task.created_at.asc())
        result = await self.db.execute(stmt)
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

    async def list_org_members(
        self, organization_id: uuid.UUID
    ) -> Sequence[tuple[User, str]]:
        """Return ``(User, role)`` pairs for the organization's active members."""

        result = await self.db.execute(
            select(User, OrganizationMember.role)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(
                OrganizationMember.organization_id == organization_id,
                User.is_active.is_(True),
            )
            .order_by(User.full_name.asc())
        )
        return list(result.all())

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
