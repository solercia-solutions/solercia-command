"""Org role template routes.

Reads (``GET``) are available to any authenticated member of the caller's
organization; instantiation (``POST .../instantiate``) requires ``admin`` or
``manager`` (specs/org-role-templates/spec.md, "Rol member no puede
instanciar"). Responses are wrapped in a ``{data}`` envelope.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership, require_role
from app.modules.org_role_templates.schemas import (
    InstantiatedProjectRead,
    InstantiateRequest,
    OrgRoleTemplateDetailRead,
    OrgRoleTemplateRead,
)
from app.modules.org_role_templates.service import OrgRoleTemplateService
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import MemberRole

router = APIRouter(prefix="/org-role-templates", tags=["org-role-templates"])

# Module-level dependency instance (not built inline in a default) — avoids
# calling `require_role(...)` as a function-argument default, same pattern as
# `projects/router.py::_require_hierarchy_write_role`.
_require_instantiate_role = require_role(MemberRole.admin, MemberRole.manager)


@router.get("")
async def list_templates(
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List every org-role-template visible to the caller's organization.

    Today this is always the 5 seeded system templates
    (``organization_id IS NULL``) — visible to every organization.
    """

    service = OrgRoleTemplateService(db)
    templates = await service.list_templates(membership.organization_id)
    data = [OrgRoleTemplateRead.model_validate(t) for t in templates]
    return {"data": data}


@router.get("/{template_id}")
async def get_template(
    template_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a single template with its full node tree.

    Returns **404** (``template_not_found``) when the template does not
    exist or is not visible to the caller's organization.
    """

    service = OrgRoleTemplateService(db)
    template, tree = await service.get_template_tree(
        membership.organization_id, template_id
    )
    payload = OrgRoleTemplateDetailRead.model_validate(
        {
            "id": template.id,
            "name": template.name,
            "is_system": template.is_system,
            "tree": tree,
        }
    )
    return {"data": payload}


@router.post("/{template_id}/instantiate", status_code=status.HTTP_201_CREATED)
async def instantiate_template(
    template_id: uuid.UUID,
    payload: InstantiateRequest,
    membership: OrganizationMember = Depends(_require_instantiate_role),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Instantiate (or reconcile) the template's project tree.

    Every generated/reconciled project gets ``lead_user_id = payload.
    lead_user_id`` and ``parent_project_id`` chained per the template's tree
    (specs/org-role-templates/spec.md, R2). Returns **422**
    (``lead_not_member``) when ``lead_user_id`` is not an active member of
    the caller's organization, or **404** (``template_not_found``) when the
    template does not exist or is not visible — in both cases NO project is
    created (R4). Requires ``admin`` or ``manager`` — any other role gets
    **403** (``forbidden``).
    """

    service = OrgRoleTemplateService(db)
    projects = await service.instantiate(
        membership.organization_id,
        template_id,
        payload.lead_user_id,
        actor_id=actor_id,
    )
    data = [InstantiatedProjectRead.model_validate(p) for p in projects]
    return {"data": data}
