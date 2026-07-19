"""Business logic for connectors — CRUD use-cases (change 14-integration-ports).

RBAC lives at the router layer (``require_role(admin, manager)`` for
writes); this service assumes the caller already passed that gate and
focuses on org-scoped persistence orchestration.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.connectors.models import Connector
from app.modules.connectors.repository import ConnectorRepository
from app.modules.connectors.schemas import ConnectorCreate, ConnectorRead, ConnectorUpdate
from app.shared.exceptions import AppException

_CONNECTOR_UPDATABLE_FIELDS = ("provider", "scopes", "status")


class ConnectorService:
    """Orchestrates connector CRUD use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = ConnectorRepository(db)

    async def create_connector(
        self,
        organization_id: uuid.UUID,
        data: ConnectorCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> ConnectorRead:
        """Create a connector (provider configuration) for the organization."""

        connector = Connector(
            organization_id=organization_id,
            provider=data.provider,
            scopes=list(data.scopes) if data.scopes is not None else None,
            status=data.status,
            created_by=actor_id,
            updated_by=actor_id,
        )
        connector = await self.repo.create(connector)
        return ConnectorRead.model_validate(connector)

    async def get_connector(
        self, organization_id: uuid.UUID, connector_id: uuid.UUID
    ) -> ConnectorRead:
        """Return a single connector scoped to the organization."""

        connector = await self._require_connector(organization_id, connector_id)
        return ConnectorRead.model_validate(connector)

    async def list_connectors(self, organization_id: uuid.UUID) -> list[ConnectorRead]:
        """Return the org's active connectors."""

        rows = await self.repo.list_connectors(organization_id)
        return [ConnectorRead.model_validate(row) for row in rows]

    async def update_connector(
        self,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        data: ConnectorUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> ConnectorRead:
        """Apply a partial update to a connector."""

        connector = await self._require_connector(organization_id, connector_id)
        changes = data.model_dump(exclude_unset=True)
        for field in _CONNECTOR_UPDATABLE_FIELDS:
            if field in changes:
                setattr(connector, field, changes[field])

        connector.updated_by = actor_id
        connector = await self.repo.save(connector)
        return ConnectorRead.model_validate(connector)

    async def delete_connector(
        self, organization_id: uuid.UUID, connector_id: uuid.UUID
    ) -> None:
        """Soft-delete a connector."""

        connector = await self._require_connector(organization_id, connector_id)
        connector.is_active = False
        connector.deleted_at = datetime.now(UTC)
        await self.repo.save(connector)

    # -- helpers -------------------------------------------------------------

    async def _require_connector(
        self, organization_id: uuid.UUID, connector_id: uuid.UUID
    ) -> Connector:
        connector = await self.repo.get(organization_id, connector_id)
        if connector is None:
            raise AppException(
                "El conector no existe o no tienes acceso a él.",
                code="connector_not_found",
                status_code=404,
            )
        return connector
