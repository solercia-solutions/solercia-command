"""Asset routes: inventory CRUD, nested licences and task links.

Reads (``GET``) are open to any member (``get_current_membership``); writes
(``POST``/``PATCH``/``DELETE``) require the RBAC ``ADMIN`` role
(``require_admin``, specs/assets/spec.md). Responses are wrapped in a
``{data[, message][, meta]}`` envelope, same as every other module.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership, require_admin
from app.modules.assets.schemas import (
    AssetCreate,
    AssetLicenseCreate,
    AssetLicenseUpdate,
    AssetTaskLink,
    AssetUpdate,
)
from app.modules.assets.service import AssetLicenseService, AssetService, AssetTaskService
from app.modules.organizations.models import OrganizationMember
from app.modules.users.models import User
from app.shared.enums import AssetCriticality, AssetStatus, AssetType
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(tags=["assets"])


@router.post("/assets", status_code=status.HTTP_201_CREATED)
async def create_asset(
    payload: AssetCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    _: User = Depends(require_admin),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create an information asset (admin only)."""

    service = AssetService(db)
    asset = await service.create_asset(
        membership.organization_id, payload, actor_id=actor_id
    )
    return {"data": asset, "message": "Activo creado."}


@router.get("/assets")
async def list_assets(
    asset_type: AssetType | None = Query(default=None),
    status_filter: AssetStatus | None = Query(default=None, alias="status"),
    criticality: AssetCriticality | None = Query(default=None),
    responsible_id: uuid.UUID | None = Query(default=None),
    category: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Búsqueda por subcadena en el nombre."),
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the organization's active assets (opt-in pagination + filters)."""

    service = AssetService(db)
    assets, total = await service.list_assets(
        membership.organization_id,
        asset_type=asset_type,
        status=status_filter,
        criticality=criticality,
        responsible_id=responsible_id,
        category=category,
        q=q,
        pagination=pagination,
    )
    return {
        "data": assets,
        "message": "Activos obtenidos.",
        "meta": build_list_meta(pagination, total),
    }


@router.get("/assets/{asset_id}")
async def get_asset(
    asset_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single asset. 404 if it does not exist or is not the caller's."""

    service = AssetService(db)
    asset = await service.get_asset(membership.organization_id, asset_id)
    return {"data": asset}


@router.patch("/assets/{asset_id}")
async def update_asset(
    asset_id: uuid.UUID,
    payload: AssetUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    _: User = Depends(require_admin),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Edit an asset (admin only)."""

    service = AssetService(db)
    asset = await service.update_asset(
        membership.organization_id, asset_id, payload, actor_id=actor_id
    )
    return {"data": asset, "message": "Activo actualizado."}


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete an asset. Cascades the soft-delete to its licences (admin only)."""

    service = AssetService(db)
    await service.delete_asset(membership.organization_id, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/assets/{asset_id}/licenses", status_code=status.HTTP_201_CREATED)
async def create_asset_license(
    asset_id: uuid.UUID,
    payload: AssetLicenseCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    _: User = Depends(require_admin),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a licence for an asset (admin only). 422 if dates are invalid."""

    service = AssetLicenseService(db)
    license_row = await service.create_license(
        membership.organization_id, asset_id, payload, actor_id=actor_id
    )
    return {"data": license_row, "message": "Licencia creada."}


@router.get("/assets/{asset_id}/licenses")
async def list_asset_licenses(
    asset_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List an asset's active licences."""

    service = AssetLicenseService(db)
    licenses = await service.list_licenses(membership.organization_id, asset_id)
    return {"data": licenses, "meta": {"total": len(licenses)}}


@router.patch("/asset-licenses/{license_id}")
async def update_asset_license(
    license_id: uuid.UUID,
    payload: AssetLicenseUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    _: User = Depends(require_admin),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Edit a licence (admin only)."""

    service = AssetLicenseService(db)
    license_row = await service.update_license(
        membership.organization_id, license_id, payload, actor_id=actor_id
    )
    return {"data": license_row, "message": "Licencia actualizada."}


@router.delete("/asset-licenses/{license_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset_license(
    license_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete a licence (admin only)."""

    service = AssetLicenseService(db)
    await service.delete_license(membership.organization_id, license_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/assets/{asset_id}/tasks", status_code=status.HTTP_201_CREATED)
async def link_asset_task(
    asset_id: uuid.UUID,
    payload: AssetTaskLink,
    membership: OrganizationMember = Depends(get_current_membership),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Link an EXISTING task of the same organization to an asset (admin only).

    404 if the task does not exist or belongs to another organization.
    """

    service = AssetTaskService(db)
    link = await service.link_task(membership.organization_id, asset_id, payload.task_id)
    return {"data": link, "message": "Tarea vinculada."}


@router.get("/assets/{asset_id}/tasks")
async def list_asset_tasks(
    asset_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the tasks linked to an asset."""

    service = AssetTaskService(db)
    links = await service.list_tasks(membership.organization_id, asset_id)
    return {"data": links, "meta": {"total": len(links)}}


@router.delete(
    "/assets/{asset_id}/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def unlink_asset_task(
    asset_id: uuid.UUID,
    task_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Unlink a task from an asset (admin only)."""

    service = AssetTaskService(db)
    await service.unlink_task(membership.organization_id, asset_id, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
