"""Label routes: project-scoped CRUD plus task assignment.

All endpoints require authentication and are scoped to the caller's current
organization. Responses are wrapped in a ``{data, meta}`` envelope.
"""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership
from app.modules.labels.schemas import LabelCreate, LabelUpdate, TaskLabelLink
from app.modules.labels.service import LabelService
from app.modules.organizations.models import OrganizationMember
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(tags=["labels"])


@router.get("/projects/{project_id}/labels")
async def list_labels(
    project_id: uuid.UUID,
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List a project's active labels.

    Supports opt-in pagination (``page``/``size``/``sort``/``order``); without
    those params the full collection is returned unchanged.
    """

    service = LabelService(db)
    labels, total = await service.list_labels(
        membership.organization_id, project_id, pagination
    )
    return {"data": labels, "meta": build_list_meta(pagination, total)}


@router.post("/projects/{project_id}/labels", status_code=status.HTTP_201_CREATED)
async def create_label(
    project_id: uuid.UUID,
    payload: LabelCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a project-scoped label. ``name`` must be unique among active labels."""

    service = LabelService(db)
    label = await service.create_label(
        membership.organization_id, project_id, payload, actor_id=actor_id
    )
    return {"data": label}


@router.patch("/labels/{label_id}")
async def update_label(
    label_id: uuid.UUID,
    payload: LabelUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Rename or recolor a label."""

    service = LabelService(db)
    label = await service.update_label(
        membership.organization_id, label_id, payload, actor_id=actor_id
    )
    return {"data": label}


@router.delete("/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_label(
    label_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete a label and unlink it from every task it was assigned to."""

    service = LabelService(db)
    await service.delete_label(membership.organization_id, label_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/tasks/{task_id}/labels", status_code=status.HTTP_201_CREATED)
async def assign_label(
    task_id: uuid.UUID,
    payload: TaskLabelLink,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Assign a label to a task. Both must belong to the same project (422)."""

    service = LabelService(db)
    await service.assign_label(membership.organization_id, task_id, payload.label_id)
    labels = await service.list_labels_for_task(task_id)
    return {"data": labels, "meta": {"total": len(labels)}}


@router.delete(
    "/tasks/{task_id}/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def unassign_label(
    task_id: uuid.UUID,
    label_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Unassign a label from a task."""

    service = LabelService(db)
    await service.unassign_label(membership.organization_id, task_id, label_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
