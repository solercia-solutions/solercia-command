"""Global search routes: ``GET /search`` across tasks, projects and comments.

Requires authentication and is scoped to the caller's current organization.
Any member role can search — no additional role restriction (global-search.md
R6). Response is wrapped in the shared ``{data, message, meta}`` envelope.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_membership
from app.modules.organizations.models import OrganizationMember
from app.modules.search.service import SearchService
from app.shared.pagination import PaginationParams, pagination_params

router = APIRouter(tags=["search"])


@router.get("/search")
async def search(
    q: str = Query(..., description="Texto a buscar (mínimo 2 caracteres)."),
    types: str | None = Query(
        default=None,
        description="Lista separada por comas entre task, project, comment.",
    ),
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Search tasks, projects and comments within the caller's organization.

    Unlike the rest of the API (opt-in pagination, 02-contrato-api), this
    endpoint ALWAYS paginates: ``meta`` carries ``page``/``size``/``total``
    even when the caller omits ``page``/``size`` (design.md, "NOTA de
    paginación" — exclusive exception for this endpoint).
    """

    service = SearchService(db)
    results, total = await service.search(
        membership.organization_id, q, types, pagination
    )
    return {
        "data": results,
        "meta": {
            "page": pagination.page or 1,
            "size": pagination.size,
            "total": total,
        },
    }
