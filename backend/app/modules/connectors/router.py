"""Connector routes: CRUD + OAuth flow with RBAC (change 14-integration-ports).

Writes (``POST``/``PATCH``/``DELETE`` on ``/connectors``) require
``require_role(admin, manager)`` — the PRIMER consumidor real de esta
dependencia (``app/dependencies.py``, distinta del RBAC ``require_admin``
que usan ``assets``). Reads (``GET``) are open to any authenticated member
(``get_current_membership``) — a member needs to know what it CAN connect
before it has admin/manager rights. ``GET /connectors/{id}/authorize`` is a
browser navigation (membership only, ``302`` to the IdP); ``GET
/connectors/oauth/callback`` is a GLOBAL, UNAUTHENTICATED route validated
entirely by ``state`` (design.md, "redirect_uri OAuth debe ser estático").
Responses follow the standard ``{data[, message][, meta]}`` envelope.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership, require_role
from app.modules.connectors.schemas import ConnectorCreate, ConnectorUpdate
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
    """Create a connector — provider configuration (admin or manager only)."""

    service = ConnectorService(db)
    connector = await service.create_connector(
        membership.organization_id, payload, actor_id=actor_id
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
