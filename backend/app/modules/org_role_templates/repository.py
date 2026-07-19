"""Data-access layer for org role templates.

Only this layer talks to SQLAlchemy; the service depends on it.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.org_role_templates.models import (
    OrgRoleTemplate,
    OrgRoleTemplateInstantiation,
    OrgRoleTemplateNode,
)
from app.modules.organizations.models import OrganizationMember


class OrgRoleTemplateRepository:
    """Async repository encapsulating org-role-template persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_visible(
        self, organization_id: uuid.UUID
    ) -> Sequence[OrgRoleTemplate]:
        """Return every active template visible to ``organization_id``.

        System templates (``organization_id IS NULL``) are visible to every
        organization; an org-scoped template (not seeded today, but the
        column supports it) is visible only to its own organization.
        """

        result = await self.db.execute(
            select(OrgRoleTemplate)
            .where(
                OrgRoleTemplate.is_active.is_(True),
                or_(
                    OrgRoleTemplate.organization_id.is_(None),
                    OrgRoleTemplate.organization_id == organization_id,
                ),
            )
            .order_by(OrgRoleTemplate.name.asc())
        )
        return result.scalars().all()

    async def get_visible(
        self, organization_id: uuid.UUID, template_id: uuid.UUID
    ) -> OrgRoleTemplate | None:
        """Return a single template visible to ``organization_id``, or ``None``."""

        result = await self.db.execute(
            select(OrgRoleTemplate).where(
                OrgRoleTemplate.id == template_id,
                OrgRoleTemplate.is_active.is_(True),
                or_(
                    OrgRoleTemplate.organization_id.is_(None),
                    OrgRoleTemplate.organization_id == organization_id,
                ),
            )
        )
        return result.scalar_one_or_none()

    async def nodes_for_template(
        self, template_id: uuid.UUID
    ) -> Sequence[OrgRoleTemplateNode]:
        """Return every node of ``template_id`` (flat; the service orders
        the tree via ``order_parent_first``)."""

        result = await self.db.execute(
            select(OrgRoleTemplateNode).where(
                OrgRoleTemplateNode.template_id == template_id
            )
        )
        return result.scalars().all()

    async def is_org_member(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Return whether ``user_id`` belongs to ``organization_id``."""

        result = await self.db.execute(
            select(OrganizationMember.id).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def ledger_for(
        self,
        organization_id: uuid.UUID,
        template_id: uuid.UUID,
        lead_user_id: uuid.UUID,
    ) -> dict[uuid.UUID, OrgRoleTemplateInstantiation]:
        """Return ``{node_id: ledger_row}`` for the existing instantiation of
        ``(organization_id, template_id, lead_user_id)`` — design.md
        Decision 2. The caller re-checks the referenced project's
        ``is_active`` (via ``ProjectRepository.get``) to decide reuse vs.
        reconciliation, so a soft-deleted project is never silently reused.
        """

        result = await self.db.execute(
            select(OrgRoleTemplateInstantiation).where(
                OrgRoleTemplateInstantiation.organization_id == organization_id,
                OrgRoleTemplateInstantiation.template_id == template_id,
                OrgRoleTemplateInstantiation.lead_user_id == lead_user_id,
            )
        )
        return {row.node_id: row for row in result.scalars().all()}
