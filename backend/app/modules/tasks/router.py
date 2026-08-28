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
from app.modules.tasks.schemas import (
    TaskColumnMove,
    TaskCreate,
    TaskReorder,
    TaskUpdate,
)
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
    source: str | None = Query(
        default=None,
        description="Filtra por sistema de origen exacto (ej. 'checklist_xlsx', 'jira').",
    ),
    external_key: str | None = Query(
        default=None,
        description="Filtra por clave exacta en el sistema de origen (ej. 'T-05').",
    ),
    task_type: str | None = Query(
        default=None,
        description="Filtra por tipo exacto de tarea (ej. 'epic', 'story', 'bug').",
    ),
    parent_task_id: uuid.UUID | None = Query(
        default=None,
        description=(
            "Devuelve las hijas directas de esa tarea (ej. las historias de "
            "una épica); desactiva la restricción top-level del listado."
        ),
    ),
    include_subtasks: bool = Query(
        default=False,
        description="Incluye subtareas junto a las tareas de nivel superior en el mismo listado.",
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
    with every other filter (change 10-busqueda-global, R7). ``task_type``
    filters by exact equality; ``parent_task_id`` returns the direct children
    of that task (which are never top-level, so it lifts the top-level-only
    restriction).

    ``include_subtasks`` (change 32-jerarquia-subtareas) also lifts the
    top-level-only restriction, returning subtasks flat alongside top-level
    tasks in the same ``order asc, created_at asc`` order, without nesting
    them. When ``assignee_id`` is present — with or without
    ``include_subtasks`` — any subtask assigned to that user is ALWAYS
    surfaced even if its parent is assigned to someone else; that foreign
    parent is returned too, flagged ``is_context=true`` in the response
    (deduplicated when the parent already matches the filter by itself).
    Context parents never count toward ``meta.total``.
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
        source=source,
        external_key=external_key,
        task_type=task_type,
        parent_task_id=parent_task_id,
        include_subtasks=include_subtasks,
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
    """Create a task within a project, optionally as a child of another task.

    When ``parent_task_id`` points to an ``epic`` the child keeps its
    requested ``task_type`` (``task``/``story``/``bug``/``subtask``; never a
    nested ``epic``) and may carry ``estimation_points``. Under any other
    parent the child is coerced to ``subtask`` and points are rejected.
    """

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


@router.post("/tasks/reorder")
async def reorder_tasks(
    payload: TaskReorder,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Move a task to ``sprint_id`` and reindex the destination container's
    ``order`` from ``ordered_task_ids`` in a single transaction.

    Consumed by the drag & drop view and the "Mover a…" keyboard menu
    (change 31-backlog-drag-drop). Applies the same ``closed``-sprint guard
    as ``PATCH /tasks/{id}``.
    """

    service = TaskService(db)
    task = await service.reorder_tasks(
        membership.organization_id,
        payload.task_id,
        payload.sprint_id,
        payload.ordered_task_ids,
        actor_id=actor_id,
    )
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
