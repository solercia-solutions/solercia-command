"""Business logic for user management (admin), scoped by organization."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.schemas import UserRead
from app.modules.auth.service import build_user_read
from app.modules.roles.repository import RoleRepository
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import (
    AdminUserCreate,
    AdminUserUpdate,
    UserRolesUpdate,
)
from app.shared.enums import MemberRole
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams
from app.shared.security import hash_password

# Map an RBAC role code to the tenant membership role, so the legacy
# ``OrganizationMember.role`` stays coherent with the RBAC assignment.
_CODE_TO_MEMBER_ROLE = {
    "ADMIN": MemberRole.admin,
    "MANAGER": MemberRole.manager,
}


class UserService:
    """Orchestrates user management for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = UserRepository(db)
        self.roles = RoleRepository(db)

    async def list_users(
        self,
        organization_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[list[UserRead], int]:
        """Return ``(users, total)`` — the organization's users with their roles."""

        users, total = await self.repo.list_by_org(organization_id, pagination)
        reads = [
            await build_user_read(self.db, user, organization_id) for user in users
        ]
        return reads, total

    async def get_user(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> UserRead:
        """Return a single user or raise a 404 ``AppException``."""

        user = await self._require(organization_id, user_id)
        return await build_user_read(self.db, user, organization_id)

    async def create_user(
        self, organization_id: uuid.UUID, data: AdminUserCreate
    ) -> UserRead:
        """Create a user, attach it to the org and assign its roles."""

        email = data.email.strip().lower()
        if await self.repo.get_by_email(email) is not None:
            raise AppException(
                "Ya existe un usuario con ese correo.",
                code="email_taken",
                status_code=409,
            )

        await self._verify_dependency(organization_id, data.dependency_id)
        await self._verify_role_ids(organization_id, data.role_ids)

        user = User(
            email=email,
            primer_nombre=data.primer_nombre,
            segundo_nombre=data.segundo_nombre,
            primer_apellido=data.primer_apellido,
            segundo_apellido=data.segundo_apellido,
            dependency_id=data.dependency_id,
            is_active=data.is_active,
            hashed_password=hash_password(data.password),
        )
        user = await self.repo.create(user)

        await self.repo.ensure_membership(
            organization_id, user.id, MemberRole.member
        )
        await self.roles.replace_user_roles(
            user.id, organization_id, data.role_ids
        )
        await self._sync_membership_role(organization_id, user.id)

        return await build_user_read(self.db, user, organization_id)

    async def update_user(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        data: AdminUserUpdate,
    ) -> UserRead:
        """Apply a partial update to a user."""

        user = await self._require(organization_id, user_id)
        changes = data.model_dump(exclude_unset=True)

        if "email" in changes and changes["email"] is not None:
            new_email = changes["email"].strip().lower()
            if new_email != user.email:
                existing = await self.repo.get_by_email(new_email)
                if existing is not None and existing.id != user.id:
                    raise AppException(
                        "Ya existe un usuario con ese correo.",
                        code="email_taken",
                        status_code=409,
                    )
                user.email = new_email

        if "dependency_id" in changes:
            await self._verify_dependency(
                organization_id, changes["dependency_id"]
            )
            user.dependency_id = changes["dependency_id"]

        if "password" in changes and changes["password"]:
            user.hashed_password = hash_password(changes["password"])

        for field in (
            "primer_nombre",
            "segundo_nombre",
            "primer_apellido",
            "segundo_apellido",
            "is_active",
        ):
            if field in changes:
                setattr(user, field, changes[field])

        user = await self.repo.save(user)
        return await build_user_read(self.db, user, organization_id)

    async def delete_user(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Soft-delete (deactivate) a user."""

        user = await self._require(organization_id, user_id)
        user.is_active = False
        user.deleted_at = datetime.now(UTC)
        await self.repo.save(user)

    async def replace_roles(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        data: UserRolesUpdate,
    ) -> UserRead:
        """Replace the user's roles within the organization."""

        user = await self._require(organization_id, user_id)
        await self._verify_role_ids(organization_id, data.role_ids)
        await self.roles.replace_user_roles(
            user.id, organization_id, data.role_ids
        )
        await self._sync_membership_role(organization_id, user.id)
        return await build_user_read(self.db, user, organization_id)

    # -- helpers -----------------------------------------------------------

    async def _require(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> User:
        user = await self.repo.get_in_org(organization_id, user_id)
        if user is None:
            raise AppException(
                "El usuario no existe o no pertenece a tu organización.",
                code="user_not_found",
                status_code=404,
            )
        return user

    async def _verify_dependency(
        self, organization_id: uuid.UUID, dependency_id: uuid.UUID | None
    ) -> None:
        if dependency_id is None:
            return
        if not await self.repo.dependency_belongs_to_org(
            organization_id, dependency_id
        ):
            raise AppException(
                "La dependencia indicada no existe en tu organización.",
                code="invalid_dependency",
                status_code=422,
            )

    async def _verify_role_ids(
        self, organization_id: uuid.UUID, role_ids: list[uuid.UUID]
    ) -> None:
        if not role_ids:
            return
        valid = await self.roles.validate_org_role_ids(
            organization_id, role_ids
        )
        if set(role_ids) - valid:
            raise AppException(
                "Uno o más roles indicados no existen en tu organización.",
                code="invalid_role",
                status_code=422,
            )

    async def _sync_membership_role(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Align ``OrganizationMember.role`` with the user's highest RBAC role."""

        roles = await self.roles.roles_for_user(user_id, organization_id)
        codes = {role.code for role in roles}
        member_role = MemberRole.member
        for code, mapped in _CODE_TO_MEMBER_ROLE.items():
            if code in codes:
                member_role = mapped
                break

        membership = await self.repo.get_membership(organization_id, user_id)
        if membership is not None and membership.role != member_role:
            membership.role = member_role
            await self.db.commit()
