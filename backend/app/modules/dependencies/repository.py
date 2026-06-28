"""Data-access layer for dependencies (org-scoped areas)."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.dependencies.models import Dependency


class DependencyRepository:
    """Async repository encapsulating dependency persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_org(
        self, organization_id: uuid.UUID
    ) -> Sequence[Dependency]:
        """Return active dependencies for an organization, by name."""

        result = await self.db.execute(
            select(Dependency)
            .where(
                Dependency.organization_id == organization_id,
                Dependency.is_active.is_(True),
            )
            .order_by(Dependency.name.asc())
        )
        return result.scalars().all()

    async def get(
        self, organization_id: uuid.UUID, dependency_id: uuid.UUID
    ) -> Dependency | None:
        """Return a single active dependency scoped to the organization."""

        result = await self.db.execute(
            select(Dependency).where(
                Dependency.id == dependency_id,
                Dependency.organization_id == organization_id,
                Dependency.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, dependency: Dependency) -> Dependency:
        """Persist a new dependency and return the refreshed instance."""

        self.db.add(dependency)
        await self.db.commit()
        await self.db.refresh(dependency)
        return dependency

    async def save(self, dependency: Dependency) -> Dependency:
        """Flush pending changes on an attached dependency and return it."""

        await self.db.commit()
        await self.db.refresh(dependency)
        return dependency
