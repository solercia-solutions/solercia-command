"""Data-access layer for roles and their menu grants."""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.roles.models import Role, RoleMenu, UserRole


class RoleRepository:
    """Async repository encapsulating role persistence and menu grants."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_org(self, organization_id: uuid.UUID) -> Sequence[Role]:
        """Return active roles for an organization, by name."""

        result = await self.db.execute(
            select(Role)
            .where(
                Role.organization_id == organization_id,
                Role.is_active.is_(True),
            )
            .order_by(Role.name.asc())
        )
        return result.scalars().all()

    async def get(
        self, organization_id: uuid.UUID, role_id: uuid.UUID
    ) -> Role | None:
        """Return a single active role scoped to the organization."""

        result = await self.db.execute(
            select(Role).where(
                Role.id == role_id,
                Role.organization_id == organization_id,
                Role.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(
        self, organization_id: uuid.UUID, code: str
    ) -> Role | None:
        """Return an active role by its org-unique code, or ``None``."""

        result = await self.db.execute(
            select(Role).where(
                Role.organization_id == organization_id,
                Role.code == code,
                Role.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, role: Role) -> Role:
        """Persist a new role and return the refreshed instance."""

        self.db.add(role)
        await self.db.commit()
        await self.db.refresh(role)
        return role

    async def save(self, role: Role) -> Role:
        """Flush pending changes on an attached role and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(role)
        return role

    async def menu_ids_for(self, role_id: uuid.UUID) -> list[uuid.UUID]:
        """Return the menu ids granted by a single role."""

        result = await self.db.execute(
            select(RoleMenu.menu_id).where(RoleMenu.role_id == role_id)
        )
        return list(result.scalars().all())

    async def menu_ids_for_many(
        self, role_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        """Return a ``{role_id: [menu_id, ...]}`` map for several roles."""

        mapping: dict[uuid.UUID, list[uuid.UUID]] = {rid: [] for rid in role_ids}
        if not role_ids:
            return mapping
        result = await self.db.execute(
            select(RoleMenu.role_id, RoleMenu.menu_id).where(
                RoleMenu.role_id.in_(role_ids)
            )
        )
        for role_id, menu_id in result.all():
            mapping.setdefault(role_id, []).append(menu_id)
        return mapping

    async def replace_menus(
        self, role_id: uuid.UUID, menu_ids: Sequence[uuid.UUID]
    ) -> None:
        """Replace the role's menu grants with exactly ``menu_ids``."""

        await self.db.execute(
            delete(RoleMenu).where(RoleMenu.role_id == role_id)
        )
        for menu_id in dict.fromkeys(menu_ids):
            self.db.add(RoleMenu(role_id=role_id, menu_id=menu_id))
        await self.db.commit()

    # -- user <-> role assignment (org-scoped) ----------------------------

    async def roles_for_user(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> list[Role]:
        """Return a user's active roles within an organization."""

        result = await self.db.execute(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user_id,
                Role.organization_id == organization_id,
                Role.is_active.is_(True),
            )
            .order_by(Role.name.asc())
        )
        return list(result.scalars().all())

    async def role_ids_for_user(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Return the ids of a user's active roles within an organization."""

        result = await self.db.execute(
            select(Role.id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user_id,
                Role.organization_id == organization_id,
                Role.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def validate_org_role_ids(
        self, organization_id: uuid.UUID, role_ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Return the subset of ``role_ids`` that are active roles of the org."""

        if not role_ids:
            return set()
        result = await self.db.execute(
            select(Role.id).where(
                Role.id.in_(role_ids),
                Role.organization_id == organization_id,
                Role.is_active.is_(True),
            )
        )
        return set(result.scalars().all())

    async def replace_user_roles(
        self,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        role_ids: Sequence[uuid.UUID],
    ) -> None:
        """Replace a user's role assignments **within one organization**.

        Links to roles from other organizations are left untouched so the
        operation stays tenant-isolated.
        """

        org_role_ids = (
            select(Role.id)
            .where(Role.organization_id == organization_id)
            .scalar_subquery()
        )
        await self.db.execute(
            delete(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id.in_(org_role_ids),
            )
        )
        for role_id in dict.fromkeys(role_ids):
            self.db.add(UserRole(user_id=user_id, role_id=role_id))
        await self.db.commit()
