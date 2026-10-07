"""Tenant-scoped port + SQLAlchemy adapter for ``ai_provider_settings``.

The repository never commits: ``AiSettingsService`` owns completion. Every
lookup is by ``organization_id``; there is no ``get(id)``.
"""

import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AiProviderSettings


class AiProviderSettingsRepository(Protocol):
    async def find_for_organization(
        self, organization_id: uuid.UUID
    ) -> AiProviderSettings | None: ...

    async def add(self, row: AiProviderSettings) -> None: ...


class SqlAiProviderSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_for_organization(self, organization_id: uuid.UUID) -> AiProviderSettings | None:
        return await self._session.scalar(
            select(AiProviderSettings).where(AiProviderSettings.organization_id == organization_id)
        )

    async def add(self, row: AiProviderSettings) -> None:
        """Flush so the UNIQUE(organization_id) surfaces here as an
        ``IntegrityError`` instead of at commit time."""

        self._session.add(row)
        await self._session.flush()
