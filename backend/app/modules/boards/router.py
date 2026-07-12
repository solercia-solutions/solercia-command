"""Board routes.

All endpoints require authentication and are scoped to the caller's current
organization. Responses are wrapped in a ``{data, meta}`` envelope.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership
from app.modules.boards.schemas import (
    BoardColumnCreate,
    BoardColumnRead,
    BoardColumnRename,
    BoardColumnsReorder,
    BoardRead,
)
from app.modules.boards.service import BoardService
from app.modules.organizations.models import OrganizationMember
from app.modules.projects.repository import ProjectRepository
from app.shared.exceptions import AppException

router = APIRouter(tags=["boards"])


@router.get("/projects/{project_id}/board")
async def get_project_board(
    project_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the project's board with its columns.

    The column set is a bounded, nested collection — never paginated (see
    design.md, "Exención documentada del contrato de paginación de 02").
    """

    projects = ProjectRepository(db)
    project = await projects.get(membership.organization_id, project_id)
    if project is None:
        raise AppException(
            "El proyecto no existe o no tienes acceso a él.",
            code="project_not_found",
            status_code=404,
        )

    service = BoardService(db)
    board = await service.get_board(project_id)
    if board is None:
        raise AppException(
            "El proyecto no tiene un board configurado.",
            code="board_not_found",
            status_code=404,
        )

    return {"data": BoardRead.model_validate(board)}


# NOTE: this fixed-path route must be declared BEFORE the `{column_id}` PATCH
# route below, so FastAPI does not try to coerce the literal "reorder" into a
# UUID (same pattern as tasks/router.py's `by-key/{key}`).
@router.patch("/boards/{board_id}/columns/reorder")
async def reorder_board_columns(
    board_id: uuid.UUID,
    payload: BoardColumnsReorder,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Persist a new column order for a board (boards.md, "Reordenar columnas")."""

    service = BoardService(db)
    columns = await service.reorder_columns(
        membership.organization_id, board_id, payload.ordered_ids, actor_id=actor_id
    )
    return {
        "data": [BoardColumnRead.model_validate(column) for column in columns],
        "meta": {"total": len(columns)},
    }


@router.patch("/boards/{board_id}/columns/{column_id}")
async def rename_board_column(
    board_id: uuid.UUID,
    column_id: uuid.UUID,
    payload: BoardColumnRename,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Rename a column. ``status_key`` — and every assigned task — is untouched."""

    service = BoardService(db)
    column = await service.rename_column(
        membership.organization_id, board_id, column_id, payload.name, actor_id=actor_id
    )
    return {"data": BoardColumnRead.model_validate(column)}


@router.post("/boards/{board_id}/columns", status_code=status.HTTP_201_CREATED)
async def add_board_column(
    board_id: uuid.UUID,
    payload: BoardColumnCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add a column to a board, deriving a unique ``status_key`` slug from ``name``.

    Makes ``custom`` boards usable from a zero-column state.
    """

    service = BoardService(db)
    column = await service.add_column(
        membership.organization_id,
        board_id,
        payload.name,
        payload.wip_limit,
        actor_id=actor_id,
    )
    return {"data": BoardColumnRead.model_validate(column)}


@router.delete(
    "/boards/{board_id}/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_board_column(
    board_id: uuid.UUID,
    column_id: uuid.UUID,
    target_column_id: uuid.UUID | None = Query(
        default=None,
        description=(
            "Columna destino para reasignar tareas "
            "(obligatoria si la columna tiene tareas)."
        ),
    ),
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Remove a column: soft-delete if empty, or reassign-then-delete.

    Rejects removing the LAST column of a board (422) and removing a column
    that has tasks without a valid ``target_column_id`` (409).
    """

    service = BoardService(db)
    await service.remove_column(
        membership.organization_id,
        board_id,
        column_id,
        target_column_id,
        actor_id=actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
