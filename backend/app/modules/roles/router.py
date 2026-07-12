"""Role (RBAC) admin routes.

All endpoints require an authenticated administrator (``require_admin``) and are
scoped to the caller's current organization. Responses use the ``{data, meta}``
envelope.
"""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_membership, require_admin
from app.modules.organizations.models import OrganizationMember
from app.modules.roles.schemas import (
    RoleCreate,
    RoleMenusUpdate,
    RoleUpdate,
)
from app.modules.roles.service import RoleService
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(
    prefix="/admin/roles",
    tags=["admin: roles"],
    dependencies=[Depends(require_admin)],
)


@router.get("")
async def list_roles(
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the roles of the caller's organization.

    Supports opt-in pagination (``page``/``size``/``sort``/``order``); without
    those params the full collection is returned unchanged.
    """

    service = RoleService(db)
    data, total = await service.list_roles(membership.organization_id, pagination)
    return {"data": data, "meta": build_list_meta(pagination, total)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a role within the caller's organization."""

    service = RoleService(db)
    data = await service.create_role(membership.organization_id, payload)
    return {"data": data}


@router.get("/{role_id}")
async def get_role(
    role_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a single role owned by the caller's organization."""

    service = RoleService(db)
    data = await service.get_role(membership.organization_id, role_id)
    return {"data": data}


@router.patch("/{role_id}")
async def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Apply a partial update to a role."""

    service = RoleService(db)
    data = await service.update_role(
        membership.organization_id, role_id, payload
    )
    return {"data": data}


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete a role."""

    service = RoleService(db)
    await service.delete_role(membership.organization_id, role_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{role_id}/menus")
async def replace_role_menus(
    role_id: uuid.UUID,
    payload: RoleMenusUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Replace the set of menus (activities) the role grants access to."""

    service = RoleService(db)
    data = await service.replace_menus(
        membership.organization_id, role_id, payload
    )
    return {"data": data}
