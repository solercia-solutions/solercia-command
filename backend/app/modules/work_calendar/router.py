"""HTTP surface for the work-calendar module (change 28-calendario-laboral):
calendario de empresa, override del equipo (proyecto raíz) y calendario
resuelto.

Two ``APIRouter``s share this transversal module (design.md D4) — same
prefix-per-domain convention as ``organizations_router``/``projects_router``
even though both live here: ``organization_calendar_router`` (``/organizations``)
and ``project_calendar_router`` (``/projects``).
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import (
    get_actor_id,
    get_current_membership,
    require_admin,
    require_role,
)
from app.modules.organizations.models import OrganizationMember
from app.modules.users.models import User
from app.modules.work_calendar.schemas import WorkCalendarConfig, WorkCalendarOverride
from app.modules.work_calendar.service import WorkCalendarService
from app.shared.enums import MemberRole

organization_calendar_router = APIRouter(
    prefix="/organizations", tags=["work-calendar"]
)
project_calendar_router = APIRouter(prefix="/projects", tags=["work-calendar"])

# Module-level dependency instance (not built inline in a default) — avoids
# calling `require_role(...)` as a function-argument default (ruff B008),
# same pattern as ``projects/router.py``'s ``_require_hierarchy_write_role``.
_require_project_calendar_write_role = require_role(
    MemberRole.admin, MemberRole.manager
)


@organization_calendar_router.get("/me/work-calendar")
async def get_organization_work_calendar(
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the calendar of the caller's organization (any authenticated member)."""

    service = WorkCalendarService(db)
    config = await service.get_organization_calendar(membership.organization_id)
    return {"data": config}


@organization_calendar_router.put("/me/work-calendar")
async def put_organization_work_calendar(
    payload: WorkCalendarConfig,
    admin: User = Depends(require_admin),
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Edit the company calendar — RBAC ``ADMIN`` only (same gate as theme)."""

    service = WorkCalendarService(db)
    config = await service.set_organization_calendar(
        membership.organization_id, payload, actor_id=actor_id
    )
    return {
        "data": config,
        "message": "Calendario laboral de la empresa actualizado.",
    }


@project_calendar_router.get("/{project_id}/work-calendar")
async def get_project_work_calendar(
    project_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the RAW override of ``project_id`` (``null`` if non-root/unset)."""

    service = WorkCalendarService(db)
    override = await service.get_project_override(
        membership.organization_id, project_id
    )
    return {"data": override}


@project_calendar_router.put("/{project_id}/work-calendar")
async def put_project_work_calendar(
    project_id: uuid.UUID,
    payload: WorkCalendarOverride,
    membership: OrganizationMember = Depends(_require_project_calendar_write_role),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Set or clear (``null``) the team override — root project only.

    Requires ``admin``/``manager`` (same gate as ``update_project``/
    ``reparent_project``). Rejects with ``override_requires_root`` (422)
    when ``project_id`` is not a root project.
    """

    service = WorkCalendarService(db)
    override = await service.set_project_override(
        membership.organization_id, project_id, payload, actor_id=actor_id
    )
    return {
        "data": override,
        "message": "Calendario laboral del equipo actualizado.",
    }


@project_calendar_router.get("/{project_id}/work-calendar/resolved")
async def get_resolved_project_work_calendar(
    project_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the effective calendar of ``project_id`` at any depth.

    Returns **404** (``project_not_found``) when ``project_id`` does not
    exist, is soft-deleted, or belongs to another organization.
    """

    service = WorkCalendarService(db)
    resolved = await service.get_resolved(membership.organization_id, project_id)
    return {"data": resolved}
