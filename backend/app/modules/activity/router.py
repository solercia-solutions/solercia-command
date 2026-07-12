"""Task-history routes, nested under tasks and users.

All endpoints require authentication and are scoped to the caller's current
organization. Read-only: intentionally no ``PATCH``/``DELETE`` routes exist
for a history row (activity-history.md, "Historial de solo lectura") — any
such request resolves to a routing ``404``, never an authorization error.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_membership
from app.modules.activity.service import ActivityService
from app.modules.organizations.models import OrganizationMember
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(tags=["activity"])


@router.get("/tasks/{task_id}/history")
async def list_task_history(
    task_id: uuid.UUID,
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List a task's change history, newest first by default.

    Supports opt-in pagination (``page``/``size``/``sort``/``order``); without
    those params the full collection is returned unchanged.
    """

    service = ActivityService(db)
    rows, total = await service.list_for_task(
        membership.organization_id, task_id, pagination
    )
    return {"data": rows, "meta": build_list_meta(pagination, total)}


@router.get("/users/{user_id}/activity")
async def list_user_activity(
    user_id: uuid.UUID,
    date: date | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the changes a user caused, filterable by a single day or a range."""

    service = ActivityService(db)
    rows, total = await service.list_for_actor(
        membership.organization_id,
        user_id,
        on_date=date,
        date_from=date_from,
        date_to=date_to,
        pagination=pagination,
    )
    return {"data": rows, "meta": build_list_meta(pagination, total)}
