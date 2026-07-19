"""Data-access layer for connectors and connected accounts
(change 14-integration-ports). Every query is scoped by ``organization_id``
(direct on ``Connector``/``ConnectedAccount``, or via the account's own
``organization_id`` for ``ConnectionCredentials`` — copied from the account
at creation, never joined for scoping).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.connectors.models import Connector


class ConnectorRepository:
    """Async repository encapsulating connector persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_connectors(self, organization_id: uuid.UUID) -> Sequence[Connector]:
        """Return the org's active connectors, newest first."""

        result = await self.db.execute(
            select(Connector)
            .where(
                Connector.organization_id == organization_id,
                Connector.is_active.is_(True),
            )
            .order_by(Connector.created_at.desc())
        )
        return result.scalars().all()

    async def get(
        self, organization_id: uuid.UUID, connector_id: uuid.UUID
    ) -> Connector | None:
        """Return a single active connector scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(Connector).where(
                Connector.id == connector_id,
                Connector.organization_id == organization_id,
                Connector.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, connector: Connector) -> Connector:
        """Persist a new connector and return the refreshed instance."""

        self.db.add(connector)
        await self.db.commit()
        await self.db.refresh(connector)
        return connector

    async def save(self, connector: Connector) -> Connector:
        """Flush pending changes on an attached connector and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(connector)
        return connector
