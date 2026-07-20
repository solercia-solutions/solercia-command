"""Data access for organizations (theme personalization)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization


class OrganizationRepository:
    """Queries and writes over the ``organizations`` table."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, organization_id: uuid.UUID) -> Organization | None:
        """Return the active organization or ``None``."""

        result = await self.db.execute(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def set_theme(
        self,
        organization: Organization,
        theme: dict | None,
        *,
        actor_id: uuid.UUID | None,
    ) -> Organization:
        """Persist ``theme`` (or ``None`` to reset) sealing ``updated_by``."""

        organization.theme = theme
        organization.updated_by = actor_id
        await self.db.commit()
        await self.db.refresh(organization)
        return organization
