"""Business logic for connectors — CRUD + OAuth flow use-cases
(change 14-integration-ports).

RBAC lives at the router layer (``require_role(admin, manager)`` for
writes); this service assumes the caller already passed that gate and
focuses on org-scoped persistence orchestration.

OAuth callback boundary (design.md "Data Flow"): the callback route is
GLOBAL (``GET /connectors/oauth/callback``, no ``{id}`` in the path), so
``handle_oauth_callback`` calls ``state_store.pop``/``registry.get_adapter``
DIRECTLY (mirroring design.md's Data Flow pseudocode step-by-step) instead
of ``app.integrations.oauth.handle_callback`` — that core helper takes a
FIXED adapter up front, but here the adapter is only knowable AFTER popping
the state (the state payload IS what tells us which connector/provider this
callback belongs to). ``oauth.build_authorize`` stays used as designed by
``authorize()`` below, where the adapter IS already known before the state
is generated.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.integrations import crypto, oauth, state_store
from app.integrations.registry import get_adapter
from app.modules.connectors.models import Connector
from app.modules.connectors.repository import ConnectedAccountRepository, ConnectorRepository
from app.modules.connectors.schemas import (
    AuthorizeResponse,
    ConnectedAccountRead,
    ConnectorCreate,
    ConnectorRead,
    ConnectorUpdate,
)
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import MemberRole
from app.shared.exceptions import AppException

logger = logging.getLogger("solercia.connectors")

_CONNECTOR_UPDATABLE_FIELDS = ("provider", "scopes", "status")


class ConnectorService:
    """Orchestrates connector CRUD + OAuth use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = ConnectorRepository(db)
        self.accounts = ConnectedAccountRepository(db)

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

    # -- OAuth flow ------------------------------------------------------------

    async def authorize(
        self,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        user_id: uuid.UUID,
        redirect_uri: str | None,
    ) -> AuthorizeResponse:
        """Start the OAuth handshake: generate ``state``+URL for ``connector_id``.

        404 if the connector does not exist or belongs to another
        organization (specs/connectors/spec.md, "Authorize sobre conector
        ajeno o inexistente") — raised BEFORE any ``state`` is generated.
        """

        connector = await self._require_connector(organization_id, connector_id)
        adapter = get_adapter(connector.provider)
        if adapter is None:
            raise AppException(
                "El proveedor del conector no está disponible.",
                code="provider_not_registered",
                status_code=404,
            )

        redirect = redirect_uri or settings.OAUTH_REDIRECT_ALLOWLIST[0]
        if redirect not in settings.OAUTH_REDIRECT_ALLOWLIST:
            raise AppException(
                "El redirect_uri solicitado no está permitido.",
                code="oauth_redirect_not_allowed",
                status_code=400,
            )

        state_payload = {
            "connector_id": str(connector.id),
            "organization_id": str(organization_id),
            "user_id": str(user_id),
            "redirect_uri": redirect,
        }
        _, authorize_url = await oauth.build_authorize(
            adapter,
            redirect,
            connector.scopes or [],
            state_payload=state_payload,
            ttl=settings.OAUTH_STATE_TTL_SECONDS,
        )
        return AuthorizeResponse(authorize_url=authorize_url)

    async def handle_oauth_callback(
        self, *, code: str | None, state: str | None, error: str | None
    ) -> dict:
        """Complete the OAuth handshake for the GLOBAL callback route.

        Never exposes tokens in its return value (only the connector/account
        identifiers safe for a JSON response) — the caller (router) wraps
        this dict directly in the envelope's ``data``.
        """

        if error is not None:
            raise AppException(
                "El proveedor reportó un error o el usuario canceló la "
                "autorización.",
                code="oauth_provider_error",
                status_code=400,
            )
        if state is None or code is None:
            raise AppException(
                "La solicitud de callback está incompleta.",
                code="oauth_state_invalid",
                status_code=400,
            )

        payload = await state_store.pop(state)
        if payload is None:
            raise AppException(
                "El enlace de autorización no es válido o ya expiró.",
                code="oauth_state_invalid",
                status_code=400,
            )

        organization_id = uuid.UUID(payload["organization_id"])
        connector_id = uuid.UUID(payload["connector_id"])
        user_id = uuid.UUID(payload["user_id"])
        redirect_uri = payload["redirect_uri"]

        connector = await self.repo.get(organization_id, connector_id)
        if connector is None:
            raise AppException(
                "El conector asociado a esta autorización ya no existe.",
                code="connector_not_found",
                status_code=404,
            )

        adapter = get_adapter(connector.provider)
        if adapter is None:
            raise AppException(
                "El proveedor del conector no está disponible.",
                code="provider_not_registered",
                status_code=404,
            )

        tokens = await adapter.exchange_code(code, redirect_uri)

        access_token_enc = crypto.encrypt(tokens.access_token)
        refresh_token_enc = (
            crypto.encrypt(tokens.refresh_token) if tokens.refresh_token else None
        )

        account = await self.accounts.upsert_account(
            organization_id=organization_id,
            connector_id=connector.id,
            user_id=user_id,
            external_account_id=tokens.external_account_id,
        )
        await self.accounts.save_credentials(
            connected_account_id=account.id,
            organization_id=organization_id,
            access_token_enc=access_token_enc,
            refresh_token_enc=refresh_token_enc,
            expires_at=tokens.expires_at,
            token_type="Bearer",
            scopes=list(tokens.scopes) if tokens.scopes else None,
        )

        logger.info(
            "Callback de conector procesado: connector_id=%s external_account_id=%s",
            connector.id,
            tokens.external_account_id,
        )

        return {
            "id": str(account.id),
            "connector_id": str(account.connector_id),
            "external_account_id": account.external_account_id,
            "status": account.status.value,
        }

    # -- Connected accounts ------------------------------------------------

    async def list_connected_accounts(
        self,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        membership: OrganizationMember,
    ) -> list[ConnectedAccountRead]:
        """List a connector's connected accounts.

        Admin/manager see every account of the connector; a plain member
        sees only their OWN (specs/connectors/spec.md, "Listado y
        desconexión de cuentas conectadas").
        """

        await self._require_connector(organization_id, connector_id)
        only_user_id = (
            None
            if membership.role in (MemberRole.admin, MemberRole.manager)
            else membership.user_id
        )
        rows = await self.accounts.list_accounts(
            connector_id, organization_id, only_user_id=only_user_id
        )
        return [ConnectedAccountRead.model_validate(row) for row in rows]

    async def disconnect_account(
        self,
        organization_id: uuid.UUID,
        account_id: uuid.UUID,
        membership: OrganizationMember,
    ) -> None:
        """Disconnect (soft-delete) a connected account.

        Only the account's OWNER or an admin/manager of the org may
        disconnect it; any other member gets ``403``
        (specs/connectors/spec.md, "Member no puede desconectar la cuenta
        de otro").
        """

        account = await self.accounts.get_account(organization_id, account_id)
        if account is None:
            raise AppException(
                "La cuenta conectada no existe o no tienes acceso a ella.",
                code="connected_account_not_found",
                status_code=404,
            )

        is_owner = account.user_id == membership.user_id
        is_privileged = membership.role in (MemberRole.admin, MemberRole.manager)
        if not is_owner and not is_privileged:
            raise AppException(
                "No tienes permisos para desconectar esta cuenta.",
                code="forbidden",
                status_code=403,
            )

        await self.accounts.soft_delete_account(account, actor_id=membership.user_id)

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
