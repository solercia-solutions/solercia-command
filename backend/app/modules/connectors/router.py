"""Connector routes: CRUD + OAuth flow with RBAC (change 14-integration-ports).

Writes (``POST``/``PATCH``/``DELETE`` on ``/connectors``) require
``require_role(admin, manager)`` — el SEGUNDO consumidor cableado de esta
dependencia (``app/dependencies.py``; el primero fue ``projects/router.py``,
cambio 21), distinta del RBAC ``require_admin`` que usan ``assets``. Reads
(``GET``) are open to any authenticated member
(``get_current_membership``) — a member needs to know what it CAN connect
before it has admin/manager rights. ``GET /connectors/{id}/authorize`` is a
browser navigation (membership only, ``302`` to the IdP); ``GET
/connectors/oauth/callback`` is a GLOBAL, UNAUTHENTICATED route validated
entirely by ``state`` (design.md, "redirect_uri OAuth debe ser estático").
Responses follow the standard ``{data[, message][, meta]}`` envelope.

MCP read routes (``/{connector_id}/mcp/*``, change 19-mcp-connector,
mcp-connector/spec.md "Alcance REST propuesto") are the ONE deliberate
exception to the "reads open, writes admin/manager" split above: even
``POST .../tools/{tool_name}/call`` is open to ANY authenticated member
(design.md Open Questions, "RBAC de `call_tool`: la spec ratifica cualquier
miembro — es read-only enforced") — the read-only enforcement itself lives
in ``McpResourceReader.call_tool`` (default-deny: allowlist ∩
``readOnlyHint``), not in a role check here.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership, require_role
from app.modules.connectors.schemas import (
    ApiTokenCredentials,
    ConnectorCreate,
    ConnectorUpdate,
    McpToolCallRequest,
)
from app.modules.connectors.service import ConnectorService
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import MemberRole

router = APIRouter(tags=["connectors"])

# Module-level singleton (ruff B008: `require_role(...)` builds a NEW closure
# on every call, so it must not be invoked directly inside a `Depends(...)`
# default) — every write endpoint below shares this ONE dependency instance.
require_connector_write_role = require_role(MemberRole.admin, MemberRole.manager)


@router.post("/connectors", status_code=status.HTTP_201_CREATED)
async def create_connector(
    payload: ConnectorCreate,
    membership: OrganizationMember = Depends(require_connector_write_role),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a connector — provider configuration (admin or manager only).

    For ``provider="mcp"`` the credential (a static bearer ``token``, or
    none) travels in THIS SAME request (change 19-mcp-connector,
    specs/connectors/spec.md delta) — never through the separate
    ``POST .../credentials`` step GLPI/Jira use.
    """

    service = ConnectorService(db)
    connector = await service.create_connector(
        membership.organization_id,
        payload,
        actor_id=actor_id,
        registrant_user_id=membership.user_id,
    )
    return {"data": connector, "message": "Conector creado."}


@router.get("/connectors")
async def list_connectors(
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the organization's active connectors (any authenticated member)."""

    service = ConnectorService(db)
    connectors = await service.list_connectors(membership.organization_id)
    return {"data": connectors, "meta": {"total": len(connectors)}}


@router.get("/connectors/{connector_id}")
async def get_connector(
    connector_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single connector. 404 if it does not exist or is not the caller's."""

    service = ConnectorService(db)
    connector = await service.get_connector(membership.organization_id, connector_id)
    return {"data": connector}


@router.patch("/connectors/{connector_id}")
async def update_connector(
    connector_id: uuid.UUID,
    payload: ConnectorUpdate,
    membership: OrganizationMember = Depends(require_connector_write_role),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Edit a connector (admin or manager only)."""

    service = ConnectorService(db)
    connector = await service.update_connector(
        membership.organization_id, connector_id, payload, actor_id=actor_id
    )
    return {"data": connector, "message": "Conector actualizado."}


@router.delete("/connectors/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connector(
    connector_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_connector_write_role),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete a connector (admin or manager only)."""

    service = ConnectorService(db)
    await service.delete_connector(membership.organization_id, connector_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/connectors/{connector_id}/credentials", status_code=status.HTTP_201_CREATED
)
async def register_api_token_credentials(
    connector_id: uuid.UUID,
    payload: ApiTokenCredentials,
    membership: OrganizationMember = Depends(require_connector_write_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Register direct ``api_token`` credentials for a connector (admin or
    manager only) — change 17-adapter-glpi, C17-R2. No ``state``, no
    redirection: the payload is validated against the provider and
    encrypted straight into ``ConnectionCredentials``, never echoed back."""

    service = ConnectorService(db)
    account = await service.register_api_token_credentials(
        membership.organization_id, connector_id, payload.as_mapping(), membership
    )
    return {"data": account, "message": "Credenciales registradas."}


@router.get("/connectors/{connector_id}/authorize")
async def authorize_connector(
    connector_id: uuid.UUID,
    redirect_uri: str | None = Query(default=None),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Start the OAuth handshake: browser navigation, ``302`` to the IdP.

    404 if the connector does not exist or belongs to another organization
    (``ConnectorService.authorize`` raises BEFORE any ``state`` is
    generated). ``400`` if ``redirect_uri`` is supplied but outside
    ``OAUTH_REDIRECT_ALLOWLIST`` (anti-SSRF/open-redirect).
    """

    service = ConnectorService(db)
    result = await service.authorize(
        membership.organization_id, connector_id, membership.user_id, redirect_uri
    )
    return RedirectResponse(url=result.authorize_url, status_code=status.HTTP_302_FOUND)


@router.get("/connectors/oauth/callback")
async def oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """GLOBAL OAuth callback — validated entirely by ``state`` (single-use),
    NOT by role/authentication (the browser navigating here comes straight
    from the IdP, with no bearer token attached)."""

    service = ConnectorService(db)
    account_summary = await service.handle_oauth_callback(
        code=code, state=state, error=error
    )
    return {"data": account_summary, "message": "Cuenta conectada."}


@router.get("/connectors/{connector_id}/accounts")
async def list_connected_accounts(
    connector_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List a connector's connected accounts.

    Admin/manager see every account; a plain member sees only their OWN
    (specs/connectors/spec.md). 404 if the connector does not exist or
    belongs to another organization.
    """

    service = ConnectorService(db)
    accounts = await service.list_connected_accounts(
        membership.organization_id, connector_id, membership
    )
    return {"data": accounts, "meta": {"total": len(accounts)}}


@router.delete(
    "/connected-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def disconnect_account(
    account_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Disconnect a connected account — flat route, precedent
    ``assets/router.py`` (``/asset-licenses/{license_id}``). The account's
    OWNER or an admin/manager of the org may disconnect it; any other
    member gets ``403``. 404 if the account belongs to another organization.
    """

    service = ConnectorService(db)
    await service.disconnect_account(membership.organization_id, account_id, membership)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# MCP read routes (change 19-mcp-connector, mcp-connector/spec.md "Alcance
# REST propuesto") — any authenticated member, including the gated
# `call_tool`; 404 for a foreign-org or non-`mcp` connector (module
# docstring above).
# ---------------------------------------------------------------------------


@router.get("/connectors/{connector_id}/mcp/resources")
async def list_mcp_resources(
    connector_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List an MCP server's published resources (any authenticated member)."""

    service = ConnectorService(db)
    resources = await service.list_mcp_resources(membership.organization_id, connector_id)
    return {"data": resources, "meta": {"total": len(resources)}}


@router.get("/connectors/{connector_id}/mcp/resources/read")
async def read_mcp_resource(
    connector_id: uuid.UUID,
    uri: str = Query(...),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Read a single MCP resource by ``uri`` (any member; capped by
    ``MCP_MAX_RESOURCE_BYTES``, mcp-connector/spec.md MC-R4)."""

    service = ConnectorService(db)
    content = await service.read_mcp_resource(membership.organization_id, connector_id, uri)
    return {"data": content}


@router.get("/connectors/{connector_id}/mcp/tools")
async def list_mcp_tools(
    connector_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List an MCP server's discovered tools, with ``read_only`` mirroring
    the provider's own ``readOnlyHint`` (any authenticated member)."""

    service = ConnectorService(db)
    tools = await service.list_mcp_tools(membership.organization_id, connector_id)
    return {"data": tools, "meta": {"total": len(tools)}}


@router.post("/connectors/{connector_id}/mcp/tools/{tool_name}/call")
async def call_mcp_tool(
    connector_id: uuid.UUID,
    tool_name: str,
    payload: McpToolCallRequest,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Invoke an allowlisted, read-only MCP tool (any authenticated member —
    the read-only gate is enforced server-side, mcp-connector/spec.md
    MC-R5, never by a role check here)."""

    service = ConnectorService(db)
    result = await service.call_mcp_tool(
        membership.organization_id, connector_id, tool_name, payload.arguments
    )
    return {"data": result}
