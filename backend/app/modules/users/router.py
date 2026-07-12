"""User-management (admin) routes.

All endpoints require an authenticated administrator (``require_admin``) and are
scoped to the caller's current organization. Responses use the ``{data, meta}``
envelope; user payloads never include the password hash.
"""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership, require_admin
from app.modules.organizations.models import OrganizationMember
from app.modules.users.schemas import (
    AdminUserCreate,
    AdminUserUpdate,
    UserRolesUpdate,
)
from app.modules.users.service import UserService
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(
    prefix="/admin/users",
    tags=["admin: users"],
    dependencies=[Depends(require_admin)],
)


@router.get("")
async def list_users(
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the users of the caller's organization.

    Supports opt-in pagination (``page``/``size``/``sort``/``order``); without
    those params the full collection is returned unchanged.
    """

    service = UserService(db)
    data, total = await service.list_users(membership.organization_id, pagination)
    return {"data": data, "meta": build_list_meta(pagination, total)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: AdminUserCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a user within the caller's organization."""

    service = UserService(db)
    data = await service.create_user(
        membership.organization_id, payload, actor_id=actor_id
    )
    return {"data": data}


@router.get("/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a single user owned by the caller's organization."""

    service = UserService(db)
    data = await service.get_user(membership.organization_id, user_id)
    return {"data": data}


@router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Apply a partial update to a user."""

    service = UserService(db)
    data = await service.update_user(
        membership.organization_id, user_id, payload, actor_id=actor_id
    )
    return {"data": data}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete (deactivate) a user."""

    service = UserService(db)
    await service.delete_user(membership.organization_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{user_id}/roles")
async def replace_user_roles(
    user_id: uuid.UUID,
    payload: UserRolesUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Replace the set of roles assigned to a user."""

    service = UserService(db)
    data = await service.replace_roles(
        membership.organization_id, user_id, payload
    )
    return {"data": data}
