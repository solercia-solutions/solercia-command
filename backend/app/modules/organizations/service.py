"""Business logic for the per-organization theme (feat/org-theme)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.repository import OrganizationRepository
from app.shared.exceptions import AppException


class OrganizationThemeService:
    """Read/update the ThemeFile stored on the caller's organization.

    The tenant is ALWAYS the organization resolved from the JWT membership —
    never a URL parameter — so a caller can only ever touch their own theme.
    The ThemeFile itself is stored opaquely: the frontend validates the full
    schema with @solercia/ui's ``isRenderableTheme`` before applying it.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = OrganizationRepository(db)

    async def _get_organization(self, organization_id: uuid.UUID):
        organization = await self.repository.get_by_id(organization_id)
        if organization is None:
            raise AppException(
                "La organización no existe o está inactiva.",
                code="organization_not_found",
                status_code=404,
            )
        return organization

    async def get_theme(self, organization_id: uuid.UUID) -> dict | None:
        """Return the stored ThemeFile, or ``None`` when the org uses the default."""

        organization = await self._get_organization(organization_id)
        return organization.theme

    async def set_theme(
        self,
        organization_id: uuid.UUID,
        theme: dict,
        *,
        actor_id: uuid.UUID | None,
    ) -> dict:
        """Persist the ThemeFile for the organization and return it."""

        organization = await self._get_organization(organization_id)
        updated = await self.repository.set_theme(
            organization, theme, actor_id=actor_id
        )
        return updated.theme

    async def reset_theme(
        self, organization_id: uuid.UUID, *, actor_id: uuid.UUID | None
    ) -> None:
        """Clear the stored ThemeFile (back to the bundled default theme)."""

        organization = await self._get_organization(organization_id)
        await self.repository.set_theme(organization, None, actor_id=actor_id)
