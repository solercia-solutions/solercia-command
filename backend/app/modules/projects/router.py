"""Project routes.

All endpoints require authentication and are scoped to the caller's current
organization. Responses are wrapped in a ``{data, meta}`` envelope.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership, require_role
from app.modules.organizations.models import OrganizationMember
from app.modules.projects.schemas import (
    ProjectCreate,
    ProjectProgressNode,
    ProjectRead,
    ProjectTreeNode,
    ProjectUpdate,
    ReparentRequest,
)
from app.modules.projects.service import ProjectService
from app.modules.sprints.service import SprintService
from app.shared.enums import MemberRole
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(prefix="/projects", tags=["projects"])

# Module-level dependency instance (not built inline in a default) — avoids
# calling `require_role(...)` as a function-argument default, which ruff's
# B008 flags since `require_role` itself is not in the FastAPI marker
# whitelist (see pyproject.toml, extend-immutable-calls).
_require_hierarchy_write_role = require_role(MemberRole.admin, MemberRole.manager)


@router.get("")
async def list_projects(
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the projects of the caller's organization.

    Supports opt-in pagination (``page``/``size``/``sort``/``order``); without
    those params the full collection is returned unchanged.
    """

    service = ProjectService(db)
    projects, total = await service.list_projects(
        membership.organization_id, pagination
    )
    data = [ProjectRead.model_validate(project) for project in projects]
    return {"data": data, "meta": build_list_meta(pagination, total)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a project within the caller's organization."""

    service = ProjectService(db)
    project = await service.create_project(
        membership.organization_id, payload, actor_id=actor_id
    )
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


@router.patch("/{project_id}")
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    membership: OrganizationMember = Depends(_require_hierarchy_write_role),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Edit a project's ``name``, ``description`` and/or ``code``.

    Partial update: only the fields present in the payload are applied.
    Requires ``admin`` or ``manager`` (same write guard as the reparent,
    R7); any other role gets **403** (``forbidden``). Rejections use the
    standard envelope (``{detail, code, status}``):

    - ``methodology_not_editable`` (**422**) — ``methodology`` was sent; it
      is never editable because the seeded board and the task statuses
      depend on the Strategy.
    - ``project_code_taken`` (**409**) — the new ``code`` is already used by
      ANOTHER project of the organization (the project's own current code is
      always accepted).
    - ``project_not_found`` (**404**) — the project does not exist, is
      soft-deleted or belongs to another organization.
    """

    service = ProjectService(db)
    project = await service.update_project(
        membership.organization_id, project_id, payload, actor_id=actor_id
    )
    return {
        "data": ProjectRead.model_validate(project),
        "message": "Proyecto actualizado.",
    }


@router.patch("/{project_id}/parent")
async def reparent_project(
    project_id: uuid.UUID,
    payload: ReparentRequest,
    membership: OrganizationMember = Depends(_require_hierarchy_write_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reparent a project, or unlink it to root with ``parent_project_id: null``.

    Requires ``admin`` or ``manager`` (structural mutation, R7); any other
    role gets **403** (``forbidden``). ``payload.parent_project_id: null``
    always succeeds (unlinking can only shorten the chain, never needs
    validation). A non-null value runs the full hierarchy check
    (``ProjectService.validate_parent``) and rejects with a DISTINCT ``code``
    per cause (envelope ``{detail, code, status}``, R9):

    - ``self_parent`` (**422**) — ``parent_project_id`` equals the project's
      own id.
    - ``parent_not_found`` (**404**) — the parent does not exist, belongs to
      another organization, or is soft-deleted.
    - ``project_cycle`` (**409**) — the parent is inside the project's own
      subtree; the assignment would make it its own ancestor.
    - ``max_depth_exceeded`` (**422**) — the resulting chain would exceed
      ``PROJECT_HIERARCHY_MAX_DEPTH`` levels (default 5).

    A rejected reparent leaves the existing hierarchy UNCHANGED — see
    ``specs/project-hierarchy/spec.md``.
    """

    service = ProjectService(db)
    project = await service.reparent(
        membership.organization_id, project_id, payload.parent_project_id
    )
    return {"data": ProjectRead.model_validate(project), "message": "Proyecto reasignado."}


@router.get("/{project_id}/tree")
async def get_project_tree(
    project_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return ``project_id`` nested with every active descendant.

    Available to any authenticated member of the organization — no role
    restriction (R7), same as the rest of the ``projects`` reads. Returns
    **404** (``project_not_found``) when ``project_id`` does not exist, is
    soft-deleted, or belongs to another organization — the tree NEVER
    crosses the tenant boundary, even transitively through a descendant.
    """

    service = ProjectService(db)
    tree = await service.get_tree(membership.organization_id, project_id)
    return {"data": ProjectTreeNode.model_validate(tree)}


@router.get("/{project_id}/progress")
async def get_project_progress(
    project_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the consolidated (roll-up) progress of ``project_id``'s subtree.

    ``self`` is the project's OWN task counts (``done``/``total``/
    ``percent_done``); ``rollup`` sums the project and every active
    descendant of its subtree (design.md Decision 1/2). ``done`` is computed
    per node against ITS OWN methodology's last board column — a
    mixed-methodology subtree aggregates correctly. ``cancelled`` tasks are
    excluded from both ``done`` and ``total``. Available to any authenticated
    member of the organization — no role restriction (R7). Returns **404**
    (``project_not_found``) when ``project_id`` does not exist, is
    soft-deleted, or belongs to another organization.
    """

    service = ProjectService(db)
    progress = await service.get_progress(membership.organization_id, project_id)
    return {"data": ProjectProgressNode.model_validate(progress)}


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
