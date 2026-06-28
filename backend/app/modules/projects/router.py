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
