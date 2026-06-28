"""Executive dashboard routes.

Requires authentication; all metrics are scoped to the caller's current
organization and wrapped in a ``{data}`` envelope.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_membership
from app.modules.dashboard.service import DashboardService
from app.modules.organizations.models import OrganizationMember

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/executive")
async def executive_dashboard(
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the executive ("vista de jefe") summary for the organization."""

    service = DashboardService(db)
    data = await service.executive(membership.organization_id)
    return {"data": data}


@router.get("/performance")
async def performance_dashboard(
    sprint_id: uuid.UUID | None = None,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return per-collaborator performance metrics for the organization.

    Pass ``sprint_id`` to restrict the figures to a single sprint's tasks.
    """

    service = DashboardService(db)
    data = await service.performance(membership.organization_id, sprint_id)
    return {"data": data}
