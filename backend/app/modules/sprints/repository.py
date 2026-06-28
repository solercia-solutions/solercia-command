"""Data-access layer for sprints.

Sprints are scoped to an organization transitively through their project.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import Project
from app.modules.sprints.models import Sprint
from app.modules.tasks.models import Task


class SprintRepository:
    """Async repository encapsulating sprint persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Sequence[Sprint]:
        """Return active sprints of a project, newest first."""

        result = await self.db.execute(
            select(Sprint)
            .join(Project, Project.id == Sprint.project_id)
            .where(
                Sprint.project_id == project_id,
                Project.organization_id == organization_id,
                Sprint.is_active.is_(True),
            )
            .order_by(Sprint.created_at.desc())
        )
        return result.scalars().all()

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
