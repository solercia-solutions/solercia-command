"""GitLab integration routes.

- ``GET /gitlab/repositories`` and ``GET|PUT /gitlab/projects/{id}/repositories``
  configure which GitLab repositories belong to a Command project: admin or
  manager only (same RBAC as connector writes).
- ``GET /tasks/{id}/gitlab/activity`` reads, live, the merge requests and
  commits that mention the task key: any member of the organization, the
  same visibility as ``GET /tasks/{id}``.

Responses follow the standard ``{data[, message][, meta]}`` envelope.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership, require_role
from app.modules.gitlab_integration.schemas import ProjectRepositoriesUpdate
from app.modules.gitlab_integration.service import GitlabIntegrationService
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import MemberRole

router = APIRouter(tags=["gitlab"])

require_gitlab_config_role = require_role(MemberRole.admin, MemberRole.manager)


@router.get("/gitlab/repositories")
async def list_gitlab_repositories(
    membership: OrganizationMember = Depends(require_gitlab_config_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the GitLab repositories the organization's token can read
    (admin or manager only)."""

    repositories = await GitlabIntegrationService(db).list_repositories(membership.organization_id)
    return {"data": repositories, "meta": {"total": len(repositories)}}


@router.get("/gitlab/projects/{project_id}/repositories")
async def get_project_repositories(
    project_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_gitlab_config_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the GitLab repositories linked to a project (admin or manager)."""

    result = await GitlabIntegrationService(db).get_project_repositories(
        membership.organization_id, project_id
    )
    return {"data": result}


@router.put("/gitlab/projects/{project_id}/repositories")
async def set_project_repositories(
    project_id: uuid.UUID,
    payload: ProjectRepositoriesUpdate,
    membership: OrganizationMember = Depends(require_gitlab_config_role),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Replace the GitLab repositories linked to a project (admin or manager).
    An empty list removes the link."""

    result = await GitlabIntegrationService(db).set_project_repositories(
        membership.organization_id, project_id, payload.repositories, actor_id=actor_id
    )
    return {"data": result, "message": "Repositorios vinculados."}


@router.get("/tasks/{task_id}/gitlab/activity")
async def get_task_gitlab_activity(
    task_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Merge requests and commits in the project's linked repositories that
    mention the task key (any member of the organization; read-only, live)."""

    result = await GitlabIntegrationService(db).get_task_activity(
        membership.organization_id, task_id
    )
    return {"data": result}
