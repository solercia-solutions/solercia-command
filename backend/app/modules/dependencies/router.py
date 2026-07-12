"""Dependency (area) admin routes.

All endpoints require an authenticated administrator (``require_admin``) and are
scoped to the caller's current organization. Responses use the ``{data, meta}``
envelope.
"""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership, require_admin
from app.modules.dependencies.schemas import (
    DependencyCreate,
    DependencyRead,
    DependencyUpdate,
)
from app.modules.dependencies.service import DependencyService
from app.modules.organizations.models import OrganizationMember
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(
    prefix="/admin/dependencies",
    tags=["admin: dependencies"],
    dependencies=[Depends(require_admin)],
)


@router.get("")
async def list_dependencies(
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the dependencies of the caller's organization.

    Supports opt-in pagination (``page``/``size``/``sort``/``order``); without
    those params the full collection is returned unchanged.
    """

    service = DependencyService(db)
    items, total = await service.list_dependencies(
        membership.organization_id, pagination
    )
    data = [DependencyRead.model_validate(item) for item in items]
    return {"data": data, "meta": build_list_meta(pagination, total)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_dependency(
    payload: DependencyCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a dependency within the caller's organization."""

    service = DependencyService(db)
    item = await service.create_dependency(
        membership.organization_id, payload, actor_id=actor_id
    )
    return {"data": DependencyRead.model_validate(item)}


@router.get("/{dependency_id}")
async def get_dependency(
    dependency_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a single dependency owned by the caller's organization."""

    service = DependencyService(db)
    item = await service.get_dependency(membership.organization_id, dependency_id)
    return {"data": DependencyRead.model_validate(item)}


@router.patch("/{dependency_id}")
async def update_dependency(
    dependency_id: uuid.UUID,
    payload: DependencyUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Apply a partial update to a dependency."""

    service = DependencyService(db)
    item = await service.update_dependency(
        membership.organization_id, dependency_id, payload, actor_id=actor_id
    )
    return {"data": DependencyRead.model_validate(item)}


@router.delete("/{dependency_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dependency(
    dependency_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete a dependency."""

    service = DependencyService(db)
    await service.delete_dependency(membership.organization_id, dependency_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
