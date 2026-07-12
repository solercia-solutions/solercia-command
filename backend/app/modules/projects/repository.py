"""Data-access layer for projects.

Only this layer talks to SQLAlchemy; services and routers depend on it.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.projects.models import Project
from app.shared.pagination import PaginationParams, paginate

# Whitelist for ``?sort=`` on ``GET /projects``. First entry is the default
# order when pagination is requested without an explicit ``sort``.
SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "created_at": Project.created_at,
    "name": Project.name,
    "code": Project.code,
}


class ProjectRepository:
    """Async repository encapsulating project persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_org(
        self,
        organization_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[Project], int]:
        """Return ``(projects, total)`` — active projects, newest first."""

        stmt = select(Project).where(
            Project.organization_id == organization_id,
            Project.is_active.is_(True),
        )

        if pagination is not None and pagination.requested:
            return await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)

        stmt = stmt.order_by(Project.created_at.desc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return rows, len(rows)

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

    async def get_by_code(
        self, organization_id: uuid.UUID, code: str
    ) -> Project | None:
        """Return the active project matching ``code`` within the organization."""

        result = await self.db.execute(
            select(Project).where(
                Project.organization_id == organization_id,
                Project.code == code.upper(),
                Project.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def code_exists(
        self, organization_id: uuid.UUID, code: str, exclude_id: uuid.UUID | None = None
    ) -> bool:
        """Return True if ``code`` is already used in the organization."""

        stmt = select(Project.id).where(
            Project.organization_id == organization_id,
            Project.code == code.upper(),
            Project.is_active.is_(True),
        )
        if exclude_id is not None:
            stmt = stmt.where(Project.id != exclude_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create(self, project: Project) -> Project:
        """Persist a new project and return the refreshed instance."""

        self.db.add(project)
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def save(self, project: Project) -> Project:
        """Flush pending changes on an attached project and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(project)
        return project
