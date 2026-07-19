"""Data-access layer for connectors and connected accounts
(change 14-integration-ports). Every query is scoped by ``organization_id``
(direct on ``Connector``/``ConnectedAccount``, or via the account's own
``organization_id`` for ``ConnectionCredentials`` — copied from the account
at creation, never joined for scoping).
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials, Connector
from app.shared.enums import AccountStatus


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


class ConnectedAccountRepository:
    """Async repository encapsulating connected-account + credentials
    persistence (OAuth callback, change 14-integration-ports)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_external_id(
        self, connector_id: uuid.UUID, external_account_id: str
    ) -> ConnectedAccount | None:
        """Return the active account for ``(connector_id, external_account_id)``."""

        result = await self.db.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.connector_id == connector_id,
                ConnectedAccount.external_account_id == external_account_id,
                ConnectedAccount.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def upsert_account(
        self,
        *,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        user_id: uuid.UUID,
        external_account_id: str,
        display_name: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> ConnectedAccount:
        """Create or update the ``ConnectedAccount`` for ``external_account_id``.

        Unicidad por ``external_account_id`` DENTRO del conector (decisión
        ratificada #1): repeating the OAuth flow for the SAME external
        account updates the existing row in place — never a duplicate.
        """

        existing = await self.get_by_external_id(connector_id, external_account_id)
        if existing is not None:
            existing.status = AccountStatus.active
            existing.updated_by = actor_id
            if display_name is not None:
                existing.display_name = display_name
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        account = ConnectedAccount(
            organization_id=organization_id,
            connector_id=connector_id,
            user_id=user_id,
            external_account_id=external_account_id,
            display_name=display_name,
            status=AccountStatus.active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def get_credentials(
        self, connected_account_id: uuid.UUID
    ) -> ConnectionCredentials | None:
        """Return the (isolated) credentials row for ``connected_account_id``."""

        result = await self.db.execute(
            select(ConnectionCredentials).where(
                ConnectionCredentials.connected_account_id == connected_account_id
            )
        )
        return result.scalar_one_or_none()

    async def save_credentials(
        self,
        *,
        connected_account_id: uuid.UUID,
        organization_id: uuid.UUID,
        access_token_enc: str,
        refresh_token_enc: str | None,
        expires_at: datetime | None,
        token_type: str | None,
        scopes: list[str] | None,
    ) -> ConnectionCredentials:
        """Create or update (1:1) the encrypted credentials for an account."""

        existing = await self.get_credentials(connected_account_id)
        if existing is not None:
            existing.access_token_enc = access_token_enc
            existing.refresh_token_enc = refresh_token_enc
            existing.expires_at = expires_at
            existing.token_type = token_type
            existing.scopes = scopes
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        credentials = ConnectionCredentials(
            organization_id=organization_id,
            connected_account_id=connected_account_id,
            access_token_enc=access_token_enc,
            refresh_token_enc=refresh_token_enc,
            expires_at=expires_at,
            token_type=token_type,
            scopes=scopes,
        )
        self.db.add(credentials)
        await self.db.commit()
        await self.db.refresh(credentials)
        return credentials
