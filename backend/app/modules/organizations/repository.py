"""Data access for organizations: theme, CRUD, membership and "mine"."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.users.models import User
from app.shared.enums import MemberRole


class OrganizationRepository:
    """Queries and writes over ``organizations``/``organization_members``."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, organization_id: uuid.UUID) -> Organization | None:
        """Return the active organization or ``None``."""

        result = await self.db.execute(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Organization | None:
        """Return an organization by its unique slug, or ``None``."""

        result = await self.db.execute(
            select(Organization).where(Organization.slug == slug)
        )
        return result.scalar_one_or_none()

    async def create_with_admin(
        self, organization: Organization, *, creator_id: uuid.UUID
    ) -> Organization:
        """Persist ``organization`` and the creator's ``admin`` membership
        in a SINGLE commit (design.md Decision 4 — bootstrap transaccional).
        """

        self.db.add(organization)
        await self.db.flush()
        self.db.add(
            OrganizationMember(
                organization_id=organization.id,
                user_id=creator_id,
                role=MemberRole.admin,
            )
        )
        await self.db.commit()
        await self.db.refresh(organization)
        return organization

    async def save(self, organization: Organization) -> Organization:
        """Flush pending changes on an attached organization, refreshed."""

        await self.db.commit()
        await self.db.refresh(organization)
        return organization

    async def get_membership(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> OrganizationMember | None:
        """Return the user's membership in the organization, or ``None``."""

        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_mine(
        self, user_id: uuid.UUID
    ) -> Sequence[tuple[OrganizationMember, Organization]]:
        """Return every ``(membership, organization)`` pair for a user."""

        result = await self.db.execute(
            select(OrganizationMember, Organization)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .where(OrganizationMember.user_id == user_id)
            .order_by(Organization.name.asc())
        )
        return result.all()

    async def list_members(
        self, organization_id: uuid.UUID
    ) -> Sequence[tuple[OrganizationMember, User]]:
        """Return every ``(membership, user)`` pair for the organization."""

        result = await self.db.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(User.primer_apellido.asc(), User.primer_nombre.asc())
        )
        return result.all()

    async def get_membership_by_id(
        self, organization_id: uuid.UUID, member_id: uuid.UUID
    ) -> OrganizationMember | None:
        """Return a membership row by its own id, scoped to the organization."""

        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.id == member_id,
                OrganizationMember.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_member(self, membership: OrganizationMember) -> OrganizationMember:
        """Persist a new membership and return the refreshed instance."""

        self.db.add(membership)
        await self.db.commit()
        await self.db.refresh(membership)
        return membership

    async def save_member(
        self, membership: OrganizationMember
    ) -> OrganizationMember:
        """Flush pending changes on an attached membership, refreshed."""

        await self.db.commit()
        await self.db.refresh(membership)
        return membership

    async def remove_member(self, membership: OrganizationMember) -> None:
        """Hard-delete a membership row (MVP — no soft delete for members)."""

        await self.db.delete(membership)
        await self.db.commit()

    async def count_admins(self, organization_id: uuid.UUID) -> int:
        """Return how many ``admin`` members the organization currently has."""

        result = await self.db.execute(
            select(func.count(OrganizationMember.id)).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.role == MemberRole.admin,
            )
        )
        return result.scalar_one()

    async def set_theme(
        self,
        organization: Organization,
        theme: dict | None,
        *,
        actor_id: uuid.UUID | None,
    ) -> Organization:
        """Persist ``theme`` (or ``None`` to reset) sealing ``updated_by``."""

        organization.theme = theme
        organization.updated_by = actor_id
        await self.db.commit()
        await self.db.refresh(organization)
        return organization
