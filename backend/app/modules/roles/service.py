"""Business logic for roles (RBAC) and their menu grants."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.menus.repository import MenuRepository
from app.modules.roles.models import Role
from app.modules.roles.repository import RoleRepository
from app.modules.roles.schemas import (
    RoleCreate,
    RoleMenusUpdate,
    RoleRead,
    RoleUpdate,
)
from app.shared.exceptions import AppException


class RoleService:
    """Orchestrates role use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = RoleRepository(db)
        self.menus = MenuRepository(db)

    async def list_roles(self, organization_id: uuid.UUID) -> list[RoleRead]:
        """Return the organization's roles with their menu ids attached."""

        roles = list(await self.repo.list_by_org(organization_id))
        menu_map = await self.repo.menu_ids_for_many([role.id for role in roles])
        return [
            self._to_read(role, menu_map.get(role.id, [])) for role in roles
        ]

    async def get_role(
        self, organization_id: uuid.UUID, role_id: uuid.UUID
    ) -> RoleRead:
        """Return a single role with its menu ids, or raise a 404."""

        role = await self._require(organization_id, role_id)
        menu_ids = await self.repo.menu_ids_for(role.id)
        return self._to_read(role, menu_ids)

    async def create_role(
        self, organization_id: uuid.UUID, data: RoleCreate
    ) -> RoleRead:
        """Persist a new role, enforcing the org-unique code."""

        existing = await self.repo.get_by_code(organization_id, data.code)
        if existing is not None:
            raise AppException(
                "Ya existe un rol con ese código en tu organización.",
                code="role_code_taken",
                status_code=409,
            )
        role = Role(
            organization_id=organization_id,
            code=data.code,
            name=data.name,
        )
        role = await self.repo.create(role)
        return self._to_read(role, [])

    async def update_role(
        self,
        organization_id: uuid.UUID,
        role_id: uuid.UUID,
        data: RoleUpdate,
    ) -> RoleRead:
        """Apply a partial update to a role."""

        role = await self._require(organization_id, role_id)
        changes = data.model_dump(exclude_unset=True)

        if "code" in changes and changes["code"] != role.code:
            existing = await self.repo.get_by_code(
                organization_id, changes["code"]
            )
            if existing is not None and existing.id != role.id:
                raise AppException(
                    "Ya existe un rol con ese código en tu organización.",
                    code="role_code_taken",
                    status_code=409,
                )

        for field in ("code", "name", "is_active"):
            if field in changes:
                setattr(role, field, changes[field])
        role = await self.repo.save(role)
        menu_ids = await self.repo.menu_ids_for(role.id)
        return self._to_read(role, menu_ids)

    async def delete_role(
        self, organization_id: uuid.UUID, role_id: uuid.UUID
    ) -> None:
        """Soft-delete a role."""

        role = await self._require(organization_id, role_id)
        role.is_active = False
        role.deleted_at = datetime.now(UTC)
        await self.repo.save(role)

    async def replace_menus(
        self,
        organization_id: uuid.UUID,
        role_id: uuid.UUID,
        data: RoleMenusUpdate,
    ) -> RoleRead:
        """Replace the role's menu grants with the provided menu ids."""

        role = await self._require(organization_id, role_id)
        valid_ids = await self.menus.list_active_ids(data.menu_ids)
        missing = set(data.menu_ids) - valid_ids
        if missing:
            raise AppException(
                "Una o más actividades indicadas no existen.",
                code="invalid_menu",
                status_code=422,
            )
        await self.repo.replace_menus(role.id, data.menu_ids)
        menu_ids = await self.repo.menu_ids_for(role.id)
        return self._to_read(role, menu_ids)

    async def _require(
        self, organization_id: uuid.UUID, role_id: uuid.UUID
    ) -> Role:
        role = await self.repo.get(organization_id, role_id)
        if role is None:
            raise AppException(
                "El rol no existe o no tienes acceso a él.",
                code="role_not_found",
                status_code=404,
            )
        return role

    @staticmethod
    def _to_read(role: Role, menu_ids: list[uuid.UUID]) -> RoleRead:
        return RoleRead(
            id=role.id,
            organization_id=role.organization_id,
            code=role.code,
            name=role.name,
            is_active=role.is_active,
            created_at=role.created_at,
            menu_ids=menu_ids,
        )
