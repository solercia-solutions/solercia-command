"""glpi_sync routes: manual sync trigger + unmatched-queue resolution +
confirmed-links CRUD (change 17-adapter-glpi, UH-R3/UH-R4/UH-R5/UH-R6).

Every endpoint is gated to ``require_role(admin, manager)`` — same RBAC
shape as ``connectors``' write endpoints (design.md "Endpoints (`/api/v1/
glpi-sync`) + RBAC"). Responses follow the standard
``{data[, message][, meta]}`` envelope.
"""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.modules.glpi_sync.schemas import ResolveRequest, RunSyncRequest
from app.modules.glpi_sync.service import GlpiSyncService
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import MemberRole

router = APIRouter(prefix="/glpi-sync", tags=["glpi-sync"])

# Module-level singleton (ruff B008, same precedent as
# `connectors/router.py`'s `require_connector_write_role`).
require_glpi_sync_role = require_role(MemberRole.admin, MemberRole.manager)


@router.post("/run", status_code=status.HTTP_201_CREATED)
async def run_sync(
    payload: RunSyncRequest,
    membership: OrganizationMember = Depends(require_glpi_sync_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger a manual on-demand GLPI sync (admin or manager only)."""

    service = GlpiSyncService(db)
    result = await service.run_sync(
        membership.organization_id, payload.connector_id, membership
    )
    return {"data": result, "message": "Sincronización completada."}


@router.get("/unmatched")
async def list_unmatched(
    membership: OrganizationMember = Depends(require_glpi_sync_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the organization's pending unmatched-assignee queue."""

    service = GlpiSyncService(db)
    entries = await service.list_unmatched(membership.organization_id)
    return {"data": entries, "meta": {"total": len(entries)}}


@router.post("/unmatched/{header_id}/resolve", status_code=status.HTTP_201_CREATED)
async def resolve_unmatched(
    header_id: uuid.UUID,
    payload: ResolveRequest,
    membership: OrganizationMember = Depends(require_glpi_sync_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Resolve a queue entry: create the confirmed link and retire the
    entry from the active queue. 404 if it does not exist or belongs to
    another organization."""

    service = GlpiSyncService(db)
    link = await service.resolve_unmatched_entry(
        membership.organization_id, header_id, payload.user_id, membership
    )
    return {"data": link, "message": "Persona homologada."}


@router.post("/unmatched/{header_id}/ignore", status_code=status.HTTP_200_OK)
async def ignore_unmatched(
    header_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_glpi_sync_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ignore a queue entry without creating any link."""

    service = GlpiSyncService(db)
    await service.ignore_unmatched_entry(membership.organization_id, header_id, membership)
    return {"data": None, "message": "Entrada ignorada."}


@router.get("/links")
async def list_links(
    membership: OrganizationMember = Depends(require_glpi_sync_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the organization's confirmed GLPI person -> user links."""

    service = GlpiSyncService(db)
    links = await service.list_links(membership.organization_id)
    return {"data": links, "meta": {"total": len(links)}}


@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_link(
    link_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_glpi_sync_role),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Revoke a confirmed link — the next sync of this person re-runs the
    full cascade. 404 if it does not exist or belongs to another
    organization."""

    service = GlpiSyncService(db)
    await service.revoke_link(membership.organization_id, link_id, membership)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
