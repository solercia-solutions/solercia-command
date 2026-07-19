"""Data-access layer for connectors and connected accounts
(change 14-integration-ports). Every query is scoped by ``organization_id``
(direct on ``Connector``/``ConnectedAccount``, or via the account's own
``organization_id`` for ``ConnectionCredentials`` — copied from the account
at creation, never joined for scoping).
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import crypto
from app.integrations.dtos import OAuthTokens
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
        self,
        connector_id: uuid.UUID,
        external_account_id: str,
        *,
        include_inactive: bool = False,
    ) -> ConnectedAccount | None:
        """Return the account for ``(connector_id, external_account_id)``.

        ``include_inactive=True`` also matches a soft-deleted row —
        ``upsert_account`` needs it to REACTIVATE a previously disconnected
        account instead of colliding with
        ``uq_connected_accounts_connector_external``, which does NOT exclude
        soft-deleted rows.
        """

        conditions = [
            ConnectedAccount.connector_id == connector_id,
            ConnectedAccount.external_account_id == external_account_id,
        ]
        if not include_inactive:
            conditions.append(ConnectedAccount.is_active.is_(True))
        result = await self.db.execute(select(ConnectedAccount).where(*conditions))
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
        commit: bool = True,
    ) -> ConnectedAccount:
        """Create, update or REACTIVATE the ``ConnectedAccount`` for
        ``external_account_id``.

        Unicidad por ``external_account_id`` DENTRO del conector (decisión
        ratificada #1): repeating the OAuth flow for the SAME external
        account updates the existing row in place — never a duplicate. A
        previously disconnected (soft-deleted) row is REACTIVATED in place
        for the same reason: the UNIQUE constraint on
        ``(connector_id, external_account_id)`` does not exclude
        soft-deleted rows, so inserting a new one would collide.

        ``commit=False`` flushes instead of committing so callers needing
        atomicity across multiple writes (the OAuth callback, which also
        persists ``ConnectionCredentials``) can commit once at the end.
        """

        existing = await self.get_by_external_id(
            connector_id, external_account_id, include_inactive=True
        )
        if existing is not None:
            existing.status = AccountStatus.active
            existing.updated_by = actor_id
            if not existing.is_active:
                existing.is_active = True
                existing.deleted_at = None
            if display_name is not None:
                existing.display_name = display_name
            await self._commit_or_flush(commit)
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
        await self._commit_or_flush(commit)
        await self.db.refresh(account)
        return account

    async def _commit_or_flush(self, commit: bool) -> None:
        """``commit=True`` commits; ``commit=False`` only flushes (caller
        owns the transaction boundary — see ``upsert_account``/
        ``save_credentials``'s ``commit`` parameter)."""

        if commit:
            await self.db.commit()
        else:
            await self.db.flush()

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
        commit: bool = True,
    ) -> ConnectionCredentials:
        """Create or update (1:1) the encrypted credentials for an account.

        ``commit=False`` flushes instead of committing — see
        ``upsert_account``'s docstring: the OAuth callback commits both
        writes together, once, for atomicity.
        """

        existing = await self.get_credentials(connected_account_id)
        if existing is not None:
            existing.access_token_enc = access_token_enc
            existing.refresh_token_enc = refresh_token_enc
            existing.expires_at = expires_at
            existing.token_type = token_type
            existing.scopes = scopes
            await self._commit_or_flush(commit)
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
        await self._commit_or_flush(commit)
        await self.db.refresh(credentials)
        return credentials

    async def save_refreshed_credentials(
        self,
        connected_account_id: uuid.UUID,
        organization_id: uuid.UUID,
        tokens: OAuthTokens,
    ) -> ConnectionCredentials:
        """Persist ROTATED credentials after a successful refresh performed
        mid-read (change 22-intake-classifier, sink ``AccessContext.
        on_tokens_refreshed`` — ``app/integrations/ports.py``). Same Fernet
        mechanism as the OAuth callback (``crypto.encrypt``,
        ``handle_oauth_callback`` above).

        Called ONLY after a refresh SUCCEEDS — a caller whose refresh call
        raises never reaches this method, so existing credentials are NEVER
        overwritten with stale/corrupt data on a failed rotation (delta
        specs/connectors/spec.md, "Refresco fallido no persiste credenciales
        corruptas").
        """

        access_token_enc = crypto.encrypt(tokens.access_token)
        refresh_token_enc = (
            crypto.encrypt(tokens.refresh_token) if tokens.refresh_token else None
        )
        return await self.save_credentials(
            connected_account_id=connected_account_id,
            organization_id=organization_id,
            access_token_enc=access_token_enc,
            refresh_token_enc=refresh_token_enc,
            expires_at=tokens.expires_at,
            token_type="Bearer",
            scopes=list(tokens.scopes) if tokens.scopes else None,
        )

    async def list_accounts(
        self,
        connector_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        only_user_id: uuid.UUID | None = None,
    ) -> Sequence[ConnectedAccount]:
        """Return the connector's active accounts, newest first.

        ``only_user_id`` scopes the result to a single user's own accounts
        (member visibility, specs/connectors/spec.md) — ``None`` (admin
        or manager) returns every account of the connector.
        """

        stmt = select(ConnectedAccount).where(
            ConnectedAccount.connector_id == connector_id,
            ConnectedAccount.organization_id == organization_id,
            ConnectedAccount.is_active.is_(True),
        )
        if only_user_id is not None:
            stmt = stmt.where(ConnectedAccount.user_id == only_user_id)
        stmt = stmt.order_by(ConnectedAccount.created_at.desc())

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_account(
        self, organization_id: uuid.UUID, account_id: uuid.UUID
    ) -> ConnectedAccount | None:
        """Return a single active account scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.id == account_id,
                ConnectedAccount.organization_id == organization_id,
                ConnectedAccount.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def soft_delete_account(
        self, account: ConnectedAccount, *, actor_id: uuid.UUID | None = None
    ) -> None:
        """Soft-delete ``account`` and PURGE its isolated credentials.

        ``ConnectionCredentials`` has no soft-delete columns
        (Pk+Timestamp+Tenant only, design.md "Tablas") — disconnecting hard
        deletes the token material immediately (the account row survives
        soft-deleted for audit trail; the secret does not).
        """

        account.is_active = False
        account.deleted_at = datetime.now(UTC)
        account.updated_by = actor_id
        await self.db.execute(
            delete(ConnectionCredentials).where(
                ConnectionCredentials.connected_account_id == account.id
            )
        )
        await self.db.commit()
        await self.db.refresh(account)
