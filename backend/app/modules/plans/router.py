"""Plans routes (change 45a-planes-modelo-api, design.md D-L).

Declaration ORDER is a design decision: the whole ``/plans/activities...``
family is declared BEFORE ``/plans/{plan_id}``, otherwise ``GET
/plans/activities`` would enter through the UUID path and answer 422. Literal
order of this file:

1. GET    /plans/activities                                 (member)
2. GET    /plans/activities/conflict-counts                 (member)
3. GET    /plans/activities/{activity_id}                   (member)
4. GET    /plans/activities/{activity_id}/tasks             (member)
5. PUT    /plans/activities/{activity_id}/reports/{period}  (admin, manager)
6. POST   /plans/activities/{activity_id}/tasks             (admin, manager)
7. DELETE /plans/activities/{activity_id}/tasks/{task_id}   (admin, manager)
8. POST   /plans/activities/{activity_id}/links             (admin, manager)
9. DELETE /plans/activities/{activity_id}/links/{link_id}   (admin, manager)
10. GET   /plans                                            (member)
11. GET   /plans/{plan_id}                                  (member)

``conflict-counts`` is a literal segment, so it is declared BEFORE
``/activities/{activity_id}`` for the same reason.

There is NO route that creates a plan or an activity: the authority of a
Decreto 612 plan is its source document, not a form (design.md D10).
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership, require_role
from app.modules.organizations.models import OrganizationMember
from app.modules.plans.schemas import (
    ActivityLinkCreate,
    PlanActivityReportUpsert,
    TaskLinkCreate,
)
from app.modules.plans.service import PlansService
from app.shared.enums import MemberRole
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(prefix="/plans", tags=["plans"])

# Module-level singleton (ruff B008, same rationale as intake/router.py): every
# write endpoint below shares ONE dependency instance.
require_plans_write_role = require_role(MemberRole.admin, MemberRole.manager)


@router.get("/activities")
async def list_activities(
    plan_id: uuid.UUID | None = Query(default=None),
    plan_type: str | None = Query(default=None),
    is_mine: bool | None = Query(default=None),
    group_code: str | None = Query(default=None),
    task_id: uuid.UUID | None = Query(default=None),
    period: str | None = Query(
        default=None,
        description="Periodo (I, II, III, ANUAL) del avance reportado que se expone.",
    ),
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List activities of every plan of the organization (any member).

    Each row exposes its derived key, calculated progress, the reported
    progress of ``period`` (``null`` when not queried or without report) and
    the contributing-task count. Pagination is opt-in.
    """

    service = PlansService(db)
    activities, total = await service.list_activities(
        membership.organization_id,
        plan_id=plan_id,
        plan_type=plan_type,
        is_mine=is_mine,
        group_code=group_code,
        task_id=task_id,
        period=period,
        params=pagination,
    )
    return {"data": activities, "meta": build_list_meta(pagination, total)}


@router.get("/activities/conflict-counts")
async def list_conflict_counts(
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Per-activity count of ``conflict`` links (any member, read-only).

    Only activities with at least one conflict appear; both ends of a link
    count, so the list view can flag what needs review without loading every
    activity detail.
    """

    service = PlansService(db)
    counts = await service.list_conflict_counts(membership.organization_id)
    return {"data": counts, "meta": {"total": len(counts)}}


@router.get("/activities/{activity_id}")
async def get_activity(
    activity_id: uuid.UUID,
    period: str | None = Query(default=None),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Activity detail with its period reports and incoming/outgoing links."""

    service = PlansService(db)
    activity = await service.get_activity(membership.organization_id, activity_id, period)
    return {"data": activity}


@router.get("/activities/{activity_id}/tasks")
async def list_activity_tasks(
    activity_id: uuid.UUID,
    role: str | None = Query(default=None),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Tasks linked to an activity, optionally filtered by role."""

    service = PlansService(db)
    tasks = await service.list_activity_tasks(membership.organization_id, activity_id, role)
    return {"data": tasks, "meta": {"total": len(tasks)}}


@router.put("/activities/{activity_id}/reports/{period}")
async def upsert_report(
    activity_id: uuid.UUID,
    period: str,
    body: PlanActivityReportUpsert,
    membership: OrganizationMember = Depends(require_plans_write_role),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create or replace the self-report of a period (admin or manager).

    Idempotent: repeating the call for the same period keeps ONE row.
    """

    service = PlansService(db)
    report = await service.upsert_report(
        membership.organization_id, activity_id, period, body, actor_id
    )
    return {"data": report}


@router.post("/activities/{activity_id}/tasks", status_code=status.HTTP_201_CREATED)
async def create_task_link(
    activity_id: uuid.UUID,
    body: TaskLinkCreate,
    membership: OrganizationMember = Depends(require_plans_write_role),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Link a task to an activity with a role (admin or manager)."""

    service = PlansService(db)
    link = await service.create_task_link(membership.organization_id, activity_id, body, actor_id)
    return {"data": link}


@router.delete(
    "/activities/{activity_id}/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_task_link(
    activity_id: uuid.UUID,
    task_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_plans_write_role),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Remove the link between a task and an activity (admin or manager)."""

    service = PlansService(db)
    await service.delete_task_link(membership.organization_id, activity_id, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/activities/{activity_id}/links", status_code=status.HTTP_201_CREATED)
async def create_activity_link(
    activity_id: uuid.UUID,
    body: ActivityLinkCreate,
    membership: OrganizationMember = Depends(require_plans_write_role),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Link two activities (admin or manager).

    The resolution is ALWAYS ``manual``, whatever the client sends.
    """

    service = PlansService(db)
    link = await service.create_activity_link(
        membership.organization_id, activity_id, body, actor_id
    )
    return {"data": link}


@router.delete(
    "/activities/{activity_id}/links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_activity_link(
    activity_id: uuid.UUID,
    link_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_plans_write_role),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Remove an outgoing activity link (admin or manager)."""

    service = PlansService(db)
    await service.delete_activity_link(membership.organization_id, activity_id, link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("")
async def list_plans(
    plan_type: str | None = Query(default=None),
    period_year: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the institutional plans of the organization (any member)."""

    service = PlansService(db)
    plans, total = await service.list_plans(
        membership.organization_id,
        plan_type=plan_type,
        period_year=period_year,
        status=status_filter,
        params=pagination,
    )
    return {"data": plans, "meta": build_list_meta(pagination, total)}


@router.get("/{plan_id}")
async def get_plan(
    plan_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Plan detail with the activity count per group."""

    service = PlansService(db)
    plan = await service.get_plan(membership.organization_id, plan_id)
    return {"data": plan}
