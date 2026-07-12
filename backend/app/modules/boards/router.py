"""Board routes.

All endpoints require authentication and are scoped to the caller's current
organization. Responses are wrapped in a ``{data, meta}`` envelope.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_membership
from app.modules.boards.schemas import BoardRead
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
