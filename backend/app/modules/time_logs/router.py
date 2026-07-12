"""Time-log routes nested under tasks and users.

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
from app.modules.time_logs.schemas import TimeLogCreate, TimeLogUpdate
from app.modules.time_logs.service import TimeLogService
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(tags=["time-logs"])


@router.get("/tasks/{task_id}/time-logs")
async def list_task_time_logs(
    task_id: uuid.UUID,
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the time-log entries of a task, most recent first.

    Supports opt-in pagination (``page``/``size``/``sort``/``order``); without
    those params the full collection is returned unchanged.
    """

    service = TimeLogService(db)
    entries, total = await service.list_for_task(
        membership.organization_id, task_id, pagination
    )
    return {"data": entries, "meta": build_list_meta(pagination, total)}


@router.post("/tasks/{task_id}/time-logs", status_code=status.HTTP_201_CREATED)
async def create_time_log(
    task_id: uuid.UUID,
    payload: TimeLogCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Register time worked on a task. Always logs it for the authenticated caller."""

    service = TimeLogService(db)
    entry = await service.create_time_log(
        membership.organization_id,
        task_id,
        membership.user_id,
        payload,
        actor_id=actor_id,
    )
    return {"data": entry}


@router.patch("/time-logs/{log_id}")
async def update_time_log(
    log_id: uuid.UUID,
    payload: TimeLogUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Edit a time-log entry. Only the owner may edit their own entry."""

    service = TimeLogService(db)
    entry = await service.update_time_log(
        membership.organization_id,
        log_id,
        membership.user_id,
        payload,
        actor_id=actor_id,
    )
    return {"data": entry}


@router.delete("/time-logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_time_log(
    log_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete a time-log entry. Only the owner may delete their own entry."""

    service = TimeLogService(db)
    await service.delete_time_log(
        membership.organization_id, log_id, membership.user_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/{user_id}/time-logs")
async def list_user_time_logs(
    user_id: uuid.UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List a user's time-log entries. Self always allowed; others need admin/manager."""

    service = TimeLogService(db)
    entries, total = await service.list_for_user(
        membership.organization_id,
        user_id,
        membership.user_id,
        membership.role,
        date_from=date_from,
        date_to=date_to,
        pagination=pagination,
    )
    return {"data": entries, "meta": build_list_meta(pagination, total)}


@router.get("/users/{user_id}/time-logs/summary")
async def user_time_logs_summary(
    user_id: uuid.UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the daily/weekly hours aggregation for a user."""

    service = TimeLogService(db)
    summary = await service.summary_for_user(
        membership.organization_id,
        user_id,
        membership.user_id,
        membership.role,
        date_from=date_from,
        date_to=date_to,
    )
    return {"data": summary}
