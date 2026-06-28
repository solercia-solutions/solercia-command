"""Business logic for dependencies (org-scoped areas)."""

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.dependencies.models import Dependency
from app.modules.dependencies.repository import DependencyRepository
from app.modules.dependencies.schemas import (
    DependencyCreate,
    DependencyUpdate,
)
from app.shared.exceptions import AppException


class DependencyService:
    """Orchestrates dependency use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = DependencyRepository(db)

    async def list_dependencies(
        self, organization_id: uuid.UUID
    ) -> Sequence[Dependency]:
        """Return the organization's active dependencies."""

        return await self.repo.list_by_org(organization_id)

    async def get_dependency(
        self, organization_id: uuid.UUID, dependency_id: uuid.UUID
    ) -> Dependency:
        """Return a single dependency or raise a 404 ``AppException``."""

        return await self._require(organization_id, dependency_id)

    async def create_dependency(
        self, organization_id: uuid.UUID, data: DependencyCreate
    ) -> Dependency:
        """Persist a new dependency within the organization."""

        dependency = Dependency(
            organization_id=organization_id,
            name=data.name,
            code=data.code,
        )
        return await self.repo.create(dependency)

    async def update_dependency(
        self,
        organization_id: uuid.UUID,
        dependency_id: uuid.UUID,
        data: DependencyUpdate,
    ) -> Dependency:
        """Apply a partial update to a dependency."""

        dependency = await self._require(organization_id, dependency_id)
        changes = data.model_dump(exclude_unset=True)
        for field in ("name", "code", "is_active"):
            if field in changes:
                setattr(dependency, field, changes[field])
        return await self.repo.save(dependency)

    async def delete_dependency(
        self, organization_id: uuid.UUID, dependency_id: uuid.UUID
    ) -> None:
        """Soft-delete a dependency."""

        dependency = await self._require(organization_id, dependency_id)
        dependency.is_active = False
        dependency.deleted_at = datetime.now(timezone.utc)
        await self.repo.save(dependency)

    async def _require(
        self, organization_id: uuid.UUID, dependency_id: uuid.UUID
    ) -> Dependency:
        dependency = await self.repo.get(organization_id, dependency_id)
        if dependency is None:
            raise AppException(
                "La dependencia no existe o no tienes acceso a ella.",
                code="dependency_not_found",
                status_code=404,
            )
        return dependency
