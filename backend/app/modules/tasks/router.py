"""Task and member routes.

All endpoints require authentication and are scoped to the caller's current
organization. Responses are wrapped in a ``{data, meta}`` envelope.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership
from app.modules.organizations.models import OrganizationMember
from app.modules.tasks.schemas import TaskColumnMove, TaskCreate, TaskUpdate
from app.modules.tasks.service import TaskService
from app.shared.enums import Priority
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

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
    label_id: list[uuid.UUID] | None = Query(
        default=None, description="Repetible; unión (OR) entre etiquetas."
    ),
    priority: Priority | None = Query(default=None),
    due_from: date | None = Query(
        default=None, description="Inicio del rango de vencimiento (inclusive)."
    ),
    due_to: date | None = Query(
        default=None, description="Fin del rango de vencimiento (inclusive)."
    ),
    q: str | None = Query(
        default=None, description="Texto libre sobre título/descripción."
    ),
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List a project's top-level tasks, combining every optional filter.

    Supports opt-in pagination (``page``/``size``/``sort``/``order``); without
    those params the full collection is returned unchanged. ``label_id`` is
    repeatable (``?label_id=a&label_id=b``, OR semantics); ``priority``,
    ``due_from``/``due_to`` (range) and ``q`` (title/description) compose
    with every other filter (change 10-busqueda-global, R7).
    """

    service = TaskService(db)
    tasks, total = await service.list_tasks(
        membership.organization_id,
        project_id,
        sprint_id=sprint_id,
        status=status,
        assignee_id=assignee_id,
        label_id=label_id,
        priority=priority,
        due_from=due_from,
        due_to=due_to,
        q=q,
        pagination=pagination,
    )
    return {"data": tasks, "meta": build_list_meta(pagination, total)}


@router.post("/projects/{project_id}/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(
    project_id: uuid.UUID,
    payload: TaskCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a task (or subtask when ``parent_task_id`` is set) within a project."""

    service = TaskService(db)
    task = await service.create_task(
        membership.organization_id, project_id, payload, actor_id=actor_id
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
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Apply a partial update to a task (move column, reassign, estimate, etc.)."""

    service = TaskService(db)
    task = await service.update_task(
        membership.organization_id, task_id, payload, actor_id=actor_id
    )
    return {"data": task}


@router.patch("/tasks/{task_id}/column")
async def move_task_column(
    task_id: uuid.UUID,
    payload: TaskColumnMove,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Move a task to a different board column, deriving ``status`` from it.

    Canonical entry point for board moves (WIP-enforced; see
    ``TaskService.move_task_column``). ``PATCH /tasks/{id}`` with a plain
    ``status`` string still works and shares the same WIP-enforcing path.
    """

    service = TaskService(db)
    task = await service.move_task_column(
        membership.organization_id, task_id, payload.board_column_id, actor_id=actor_id
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
