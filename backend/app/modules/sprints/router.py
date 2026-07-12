"""Sprint routes.

All endpoints require authentication and are scoped to the caller's current
organization. Responses are wrapped in a ``{data, meta}`` envelope.
"""

import uuid

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership
from app.modules.organizations.models import OrganizationMember
from app.modules.sprints.schemas import SprintCloseBody, SprintCreate, SprintUpdate
from app.modules.sprints.service import SprintService
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(tags=["sprints"])


@router.get("/projects/{project_id}/sprints")
async def list_sprints(
    project_id: uuid.UUID,
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the sprints of a project.

    Supports opt-in pagination (``page``/``size``/``sort``/``order``); without
    those params the full collection is returned unchanged.
    """

    service = SprintService(db)
    sprints, total = await service.list_sprints(
        membership.organization_id, project_id, pagination
    )
    return {"data": sprints, "meta": build_list_meta(pagination, total)}


@router.post(
    "/projects/{project_id}/sprints", status_code=status.HTTP_201_CREATED
)
async def create_sprint(
    project_id: uuid.UUID,
    payload: SprintCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a sprint within a project."""

    service = SprintService(db)
    sprint = await service.create_sprint(
        membership.organization_id, project_id, payload, actor_id=actor_id
    )
    return {"data": sprint}


@router.get("/projects/{project_id}/sprints/{sprint_id}/burndown")
async def sprint_burndown(
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the burndown series (ideal vs actual) for a sprint."""

    service = SprintService(db)
    data = await service.burndown(
        membership.organization_id, project_id, sprint_id
    )
    return {"data": data}


@router.patch("/sprints/{sprint_id}")
async def update_sprint(
    sprint_id: uuid.UUID,
    payload: SprintUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Apply a partial update to a sprint (e.g. rename or adjust dates)."""

    service = SprintService(db)
    sprint = await service.update_sprint(
        membership.organization_id, sprint_id, payload, actor_id=actor_id
    )
    return {"data": sprint}


@router.post("/sprints/{sprint_id}/close")
async def close_sprint(
    sprint_id: uuid.UUID,
    payload: SprintCloseBody | None = Body(default=None),
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Close a sprint, compute completed story points and move incomplete tasks.

    Calling this endpoint on an already-closed sprint returns **409 Conflict**.

    Body (optional JSON):
    - ``target_sprint_id`` — UUID of another sprint in the same project to receive
      incomplete tasks. When omitted, incomplete tasks move to the backlog
      (``sprint_id = null``).

    Response includes the updated sprint and the number of tasks moved.
    """

    body = payload or SprintCloseBody()
    service = SprintService(db)
    result = await service.close_sprint(
        membership.organization_id,
        sprint_id,
        body.target_sprint_id,
        actor_id=actor_id,
    )
    return {"data": result}
