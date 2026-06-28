"""Project routes.

All endpoints require authentication and are scoped to the caller's current
organization. Responses are wrapped in a ``{data, meta}`` envelope.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_membership
from app.modules.organizations.models import OrganizationMember
from app.modules.projects.schemas import ProjectCreate, ProjectRead
from app.modules.projects.service import ProjectService
from app.modules.sprints.service import SprintService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
async def list_projects(
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the projects of the caller's organization."""

    service = ProjectService(db)
    projects = await service.list_projects(membership.organization_id)
    data = [ProjectRead.model_validate(project) for project in projects]
    return {"data": data, "meta": {"total": len(data)}}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a project within the caller's organization."""

    service = ProjectService(db)
    project = await service.create_project(membership.organization_id, payload)
    return {"data": ProjectRead.model_validate(project)}


@router.get("/{project_id}")
async def get_project(
    project_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a single project owned by the caller's organization."""

    service = ProjectService(db)
    project = await service.get_project(membership.organization_id, project_id)
    return {"data": ProjectRead.model_validate(project)}


@router.get("/{project_id}/velocity")
async def project_velocity(
    project_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the velocity report for a project.

    ``series`` — closed sprints ordered chronologically with their
    ``completed_points`` and ``closed_at`` date. Use this to plot a velocity
    trend chart.

    ``average_velocity`` — arithmetic mean of ``completed_points`` across all
    closed sprints (0.0 when no closed sprints exist yet).

    ``backlog_points`` — total estimation points in the backlog (tasks with no
    sprint and not yet completed).

    ``projected_sprints`` — estimated number of additional sprints needed to
    clear the backlog at the current average velocity. ``null`` when
    ``average_velocity`` is 0.
    """

    service = SprintService(db)
    report = await service.velocity(membership.organization_id, project_id)
    return {"data": report.model_dump()}
