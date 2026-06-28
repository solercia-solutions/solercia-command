"""Data-access layer for projects.

Only this layer talks to SQLAlchemy; services and routers depend on it.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import Project


class ProjectRepository:
    """Async repository encapsulating project persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_org(self, organization_id: uuid.UUID) -> Sequence[Project]:
        """Return active projects for an organization, newest first."""

        result = await self.db.execute(
            select(Project)
            .where(
                Project.organization_id == organization_id,
                Project.is_active.is_(True),
            )
            .order_by(Project.created_at.desc())
        )
        return result.scalars().all()

    async def get(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Project | None:
        """Return a single project scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.organization_id == organization_id,
                Project.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, project: Project) -> Project:
        """Persist a new project and return the refreshed instance."""

        self.db.add(project)
        await self.db.commit()
        await self.db.refresh(project)
        return project
