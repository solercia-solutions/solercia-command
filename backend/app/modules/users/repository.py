"""Data-access layer for user management (admin), scoped by organization.

Users belong to an organization through :class:`OrganizationMember`, so every
admin read joins on membership and filters by ``organization_id``.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.dependencies.models import Dependency
from app.modules.organizations.models import OrganizationMember
from app.modules.users.models import User
from app.shared.enums import MemberRole


class UserRepository:
    """Async repository encapsulating user persistence for the admin area."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_org(
        self, organization_id: uuid.UUID
    ) -> Sequence[User]:
        """Return every user (active or not) belonging to the organization."""

        result = await self.db.execute(
            select(User)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(User.primer_apellido.asc(), User.primer_nombre.asc())
        )
        return result.scalars().all()

    async def get_in_org(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> User | None:
        """Return a user that belongs to the organization, or ``None``."""

        result = await self.db.execute(
            select(User)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(
                User.id == user_id,
                OrganizationMember.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Return a user by email (globally unique), or ``None``."""

        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        """Persist a new user and return the refreshed instance."""

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def save(self, user: User) -> User:
        """Flush pending changes on an attached user and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_membership(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrganizationMember | None:
        """Return the user's membership in the organization, or ``None``."""

        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def ensure_membership(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role: MemberRole,
    ) -> OrganizationMember:
        """Return the membership, creating it with ``role`` when absent."""

        membership = await self.get_membership(organization_id, user_id)
        if membership is None:
            membership = OrganizationMember(
                organization_id=organization_id,
                user_id=user_id,
                role=role,
            )
            self.db.add(membership)
            await self.db.commit()
            await self.db.refresh(membership)
        return membership

    async def dependency_belongs_to_org(
        self, organization_id: uuid.UUID, dependency_id: uuid.UUID
    ) -> bool:
        """Return whether the dependency exists and belongs to the org."""

        result = await self.db.execute(
            select(Dependency.id).where(
                Dependency.id == dependency_id,
                Dependency.organization_id == organization_id,
                Dependency.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none() is not None
