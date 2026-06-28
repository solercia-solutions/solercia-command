"""Task and member routes.

All endpoints require authentication and are scoped to the caller's current
organization. Responses are wrapped in a ``{data, meta}`` envelope.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_membership
from app.modules.organizations.models import OrganizationMember
from app.modules.tasks.schemas import TaskCreate, TaskUpdate
from app.modules.tasks.service import TaskService

router = APIRouter(tags=["tasks"])


@router.get("/projects/{project_id}/members")
async def list_project_members(
    project_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the organization members assignable on a project."""

    service = TaskService(db)
    members = await service.list_members(
        membership.organization_id, project_id
    )
    return {"data": members, "meta": {"total": len(members)}}


@router.get("/projects/{project_id}/tasks")
async def list_tasks(
    project_id: uuid.UUID,
    sprint_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    assignee_id: uuid.UUID | None = Query(default=None),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List a project's top-level tasks, optionally filtered by sprint, status or assignee."""

    service = TaskService(db)
    tasks = await service.list_tasks(
        membership.organization_id,
        project_id,
        sprint_id=sprint_id,
        status=status,
        assignee_id=assignee_id,
    )
    return {"data": tasks, "meta": {"total": len(tasks)}}


@router.post("/projects/{project_id}/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(
    project_id: uuid.UUID,
    payload: TaskCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a task (or subtask when ``parent_task_id`` is set) within a project."""

    service = TaskService(db)
    task = await service.create_task(
        membership.organization_id, project_id, payload
    )
    return {"data": task}


# NOTE: this fixed-path route must be declared BEFORE the ``{task_id}`` route
# so FastAPI does not try to coerce the literal "by-key" into a UUID.
@router.get("/tasks/by-key/{key}")
async def get_task_by_key(
    key: str,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Resolve a task by its human-readable key (e.g. ``SDM-7``).

    The key format is ``{PROJECT_CODE}-{TASK_NUMBER}``. Returns the task if it
    belongs to the caller's organization.
    """

    service = TaskService(db)
    task = await service.get_task_by_key(membership.organization_id, key)
    return {"data": task}


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a single task (including subtask progress) owned by the caller's organization."""

    service = TaskService(db)
    task = await service.get_task(membership.organization_id, task_id)
    return {"data": task}


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Apply a partial update to a task (move column, reassign, estimate, etc.)."""

    service = TaskService(db)
    task = await service.update_task(
        membership.organization_id, task_id, payload
    )
    return {"data": task}


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete a task."""

    service = TaskService(db)
    await service.delete_task(membership.organization_id, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tasks/{task_id}/subtasks")
async def list_subtasks(
    task_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the direct subtasks of a task."""

    service = TaskService(db)
    subtasks = await service.list_subtasks(membership.organization_id, task_id)
    return {"data": subtasks, "meta": {"total": len(subtasks)}}
