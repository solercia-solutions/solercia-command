"""Checklist and checklist-item routes.

All endpoints require authentication and are scoped to the caller's current
organization. Responses are wrapped in a ``{data, meta}`` envelope.
"""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership
from app.modules.checklists.schemas import (
    ChecklistItemCreate,
    ChecklistItemUpdate,
    TaskChecklistCreate,
    TaskChecklistUpdate,
)
from app.modules.checklists.service import ChecklistService
from app.modules.organizations.models import OrganizationMember

router = APIRouter(tags=["checklists"])


@router.get("/tasks/{task_id}/checklists")
async def list_checklists(
    task_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List a task's active checklists, each with its ``done``/``total`` progress."""

    service = ChecklistService(db)
    checklists = await service.list_checklists(membership.organization_id, task_id)
    return {"data": checklists, "meta": {"total": len(checklists)}}


@router.post("/tasks/{task_id}/checklists", status_code=status.HTTP_201_CREATED)
async def create_checklist(
    task_id: uuid.UUID,
    payload: TaskChecklistCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a checklist on a task."""

    service = ChecklistService(db)
    checklist = await service.create_checklist(
        membership.organization_id, task_id, payload, actor_id=actor_id
    )
    return {"data": checklist}


@router.patch("/checklists/{checklist_id}")
async def update_checklist(
    checklist_id: uuid.UUID,
    payload: TaskChecklistUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Rename or reorder a checklist."""

    service = ChecklistService(db)
    checklist = await service.update_checklist(
        membership.organization_id, checklist_id, payload, actor_id=actor_id
    )
    return {"data": checklist}


@router.delete("/checklists/{checklist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_checklist(
    checklist_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete a checklist."""

    service = ChecklistService(db)
    await service.delete_checklist(membership.organization_id, checklist_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/checklists/{checklist_id}/items")
async def list_checklist_items(
    checklist_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the active items of a checklist, ordered for display."""

    service = ChecklistService(db)
    items = await service.list_items(membership.organization_id, checklist_id)
    return {"data": items, "meta": {"total": len(items)}}


@router.post("/checklists/{checklist_id}/items", status_code=status.HTTP_201_CREATED)
async def create_checklist_item(
    checklist_id: uuid.UUID,
    payload: ChecklistItemCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create an item within a checklist."""

    service = ChecklistService(db)
    item = await service.create_item(
        membership.organization_id, checklist_id, payload, actor_id=actor_id
    )
    return {"data": item}


@router.patch("/checklist-items/{item_id}")
async def update_checklist_item(
    item_id: uuid.UUID,
    payload: ChecklistItemUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Edit an item's text and/or reorder it within its checklist."""

    service = ChecklistService(db)
    item = await service.update_item(
        membership.organization_id, item_id, payload, actor_id=actor_id
    )
    return {"data": item}


@router.patch("/checklist-items/{item_id}/toggle")
async def toggle_checklist_item(
    item_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Flip an item's ``is_done`` flag."""

    service = ChecklistService(db)
    item = await service.toggle_item(
        membership.organization_id, item_id, actor_id=actor_id
    )
    return {"data": item}


@router.delete(
    "/checklist-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_checklist_item(
    item_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete an item."""

    service = ChecklistService(db)
    await service.delete_item(membership.organization_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
