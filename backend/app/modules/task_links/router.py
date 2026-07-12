"""Task dependency routes, nested under ``/tasks/{task_id}/dependencies``.

Deliberately never a flat ``/dependencies`` prefix — that path already
belongs to ``app.modules.dependencies`` (organizational areas, mounted at
``/admin/dependencies``); nesting under a task avoids any collision.
"""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_membership
from app.modules.organizations.models import OrganizationMember
from app.modules.task_links.schemas import TaskDependencyLink
from app.modules.task_links.service import TaskDependencyService
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(tags=["task-dependencies"])


@router.get("/tasks/{task_id}/dependencies")
async def list_task_dependencies(
    task_id: uuid.UUID,
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List a task's active dependency edges, both directions.

    Supports opt-in pagination (``page``/``size``/``sort``/``order``); without
    those params the full collection is returned unchanged.
    """

    service = TaskDependencyService(db)
    dependencies, total = await service.list_dependencies(
        membership.organization_id, task_id, pagination
    )
    return {"data": dependencies, "meta": build_list_meta(pagination, total)}


@router.post("/tasks/{task_id}/dependencies", status_code=status.HTTP_201_CREATED)
async def link_task_dependency(
    task_id: uuid.UUID,
    payload: TaskDependencyLink,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Link the path task to ``related_task_id``, rejecting cycles (422)."""

    service = TaskDependencyService(db)
    dependency = await service.link(membership.organization_id, task_id, payload)
    return {"data": dependency}


@router.delete(
    "/tasks/{task_id}/dependencies/{dependency_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_task_dependency(
    task_id: uuid.UUID,
    dependency_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete a dependency edge touching the task."""

    service = TaskDependencyService(db)
    await service.unlink(membership.organization_id, task_id, dependency_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
