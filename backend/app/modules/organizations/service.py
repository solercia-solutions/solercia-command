"""Business logic for organizations: theme, CRUD, membership, "mis empresas"."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.bootstrap import bootstrap_organization
from app.modules.organizations.bootstrap_uow import OrganizationBootstrapUow
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import (
    MemberCreate,
    MemberRead,
    OrganizationCreate,
    OrganizationMembership,
    OrganizationRead,
    OrganizationUpdate,
)
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.shared.enums import MemberRole
from app.shared.exceptions import AppException


class OrganizationThemeService:
    """Read/update the ThemeFile stored on the caller's organization.

    The tenant is ALWAYS the organization resolved from the JWT membership —
    never a URL parameter — so a caller can only ever touch their own theme.
    The ThemeFile itself is stored opaquely: the frontend validates the full
    schema with @solercia/ui's ``isRenderableTheme`` before applying it.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = OrganizationRepository(db)

    async def _get_organization(self, organization_id: uuid.UUID):
        organization = await self.repository.get_by_id(organization_id)
        if organization is None:
            raise AppException(
                "La organización no existe o está inactiva.",
                code="organization_not_found",
                status_code=404,
            )
        return organization

    async def get_theme(self, organization_id: uuid.UUID) -> dict | None:
        """Return the stored ThemeFile, or ``None`` when the org uses the default."""

        organization = await self._get_organization(organization_id)
        return organization.theme

    async def set_theme(
        self,
        organization_id: uuid.UUID,
        theme: dict,
        *,
        actor_id: uuid.UUID | None,
    ) -> dict:
        """Persist the ThemeFile for the organization and return it."""

        organization = await self._get_organization(organization_id)
        updated = await self.repository.set_theme(
            organization, theme, actor_id=actor_id
        )
        return updated.theme

    async def reset_theme(
        self, organization_id: uuid.UUID, *, actor_id: uuid.UUID | None
    ) -> None:
        """Clear the stored ThemeFile (back to the bundled default theme)."""

        organization = await self._get_organization(organization_id)
        await self.repository.set_theme(organization, None, actor_id=actor_id)


class OrganizationService:
    """CRUD + bootstrap + "mis empresas" (organizations-admin R1/R2/R5)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = OrganizationRepository(db)

    async def create_bootstrap(
        self,
        data: OrganizationCreate,
        *,
        creator_id: uuid.UUID,
        actor_id: uuid.UUID | None,
    ) -> OrganizationRead:
        """Compatibility facade: new tenant, creator admin and Generales atomically."""
        return await bootstrap_organization(
            OrganizationBootstrapUow(self.db), data,
            creator_id=creator_id, actor_id=actor_id,
        )

    async def list_mine(self, user_id: uuid.UUID) -> list[OrganizationMembership]:
        """Return every organization the user belongs to, with their role."""

        rows = await self.repo.list_mine(user_id)
        return [
            OrganizationMembership(
                organization=OrganizationRead.model_validate(organization),
                role=membership.role,
            )
            for membership, organization in rows
        ]

    async def get(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrganizationRead:
        """Return the organization if the caller is a member of it (404 otherwise)."""

        organization = await self._require_member(organization_id, user_id)
        return OrganizationRead.model_validate(organization)

    async def update(
        self,
        organization_id: uuid.UUID,
        data: OrganizationUpdate,
        *,
        actor_id: uuid.UUID | None,
    ) -> OrganizationRead:
        """Apply a partial update — caller must already be `require_org_admin`-gated."""

        organization = await self._get_organization(organization_id)
        changes = data.model_dump(exclude_unset=True)

        if "slug" in changes and changes["slug"] != organization.slug:
            existing = await self.repo.get_by_slug(changes["slug"])
            if existing is not None and existing.id != organization.id:
                raise AppException(
                    "Ya existe una empresa con ese identificador (slug).",
                    code="organization_slug_taken",
                    status_code=409,
                )

        for field in ("name", "slug"):
            if field in changes:
                setattr(organization, field, changes[field])
        organization.updated_by = actor_id
        organization = await self.repo.save(organization)
        return OrganizationRead.model_validate(organization)

    async def soft_delete(
        self, organization_id: uuid.UUID, *, actor_id: uuid.UUID | None
    ) -> None:
        """Deactivate the organization — caller must already be admin-gated."""

        organization = await self._get_organization(organization_id)
        organization.is_active = False
        organization.deleted_at = datetime.now(UTC)
        organization.updated_by = actor_id
        await self.repo.save(organization)

    async def _get_organization(self, organization_id: uuid.UUID) -> Organization:
        organization = await self.repo.get_by_id(organization_id)
        if organization is None:
            raise AppException(
                "La organización no existe o está inactiva.",
                code="organization_not_found",
                status_code=404,
            )
        return organization

    async def _require_member(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> Organization:
        """Return the organization only if ``user_id`` is a member of it.

        404 either way — never reveals whether the organization exists to a
        non-member (organizations-admin R2, "No miembro recibe 404 al leer").
        """

        membership = await self.repo.get_membership(user_id, organization_id)
        if membership is None:
            raise AppException(
                "La organización no existe o no tienes acceso a ella.",
                code="organization_not_found",
                status_code=404,
            )
        return await self._get_organization(organization_id)


class OrganizationMemberService:
    """Membership management within one organization (organizations-admin R2/R3)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = OrganizationRepository(db)
        self.users = UserRepository(db)

    async def list_members(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[MemberRead]:
        """List every member with their role — caller must be a member."""

        membership = await self.repo.get_membership(user_id, organization_id)
        if membership is None:
            raise AppException(
                "La organización no existe o no tienes acceso a ella.",
                code="organization_not_found",
                status_code=404,
            )
        rows = await self.repo.list_members(organization_id)
        return [self._to_read(member, user) for member, user in rows]

    async def add_member(
        self, organization_id: uuid.UUID, data: MemberCreate
    ) -> MemberRead:
        """Add an EXISTING user (found by email) — caller already admin-gated."""

        target_user = await self.users.get_by_email(data.email.strip().lower())
        if target_user is None:
            raise AppException(
                "No existe un usuario registrado con ese correo.",
                code="user_not_found",
                status_code=404,
            )

        existing = await self.repo.get_membership(target_user.id, organization_id)
        if existing is not None:
            raise AppException(
                "Ese usuario ya es miembro de la empresa.",
                code="membership_exists",
                status_code=409,
            )

        membership = OrganizationMember(
            organization_id=organization_id,
            user_id=target_user.id,
            role=data.role,
        )
        membership = await self.repo.add_member(membership)
        return self._to_read(membership, target_user)

    async def update_role(
        self,
        organization_id: uuid.UUID,
        member_id: uuid.UUID,
        new_role: MemberRole,
    ) -> MemberRead:
        """Change a member's role — rejects leaving the org without an admin."""

        membership, target_user = await self._require_membership(
            organization_id, member_id
        )

        if membership.role == MemberRole.admin and new_role != MemberRole.admin:
            await self._reject_if_last_admin(organization_id)

        membership.role = new_role
        membership = await self.repo.save_member(membership)
        return self._to_read(membership, target_user)

    async def remove_member(
        self, organization_id: uuid.UUID, member_id: uuid.UUID
    ) -> None:
        """Remove a member — rejects leaving the org without an admin."""

        membership, _ = await self._require_membership(organization_id, member_id)

        if membership.role == MemberRole.admin:
            await self._reject_if_last_admin(organization_id)

        await self.repo.remove_member(membership)

    async def _reject_if_last_admin(self, organization_id: uuid.UUID) -> None:
        admin_count = await self.repo.count_admins(organization_id)
        if admin_count <= 1:
            raise AppException(
                "La empresa debe conservar al menos un administrador.",
                code="last_admin_protected",
                status_code=409,
            )

    async def _require_membership(
        self, organization_id: uuid.UUID, member_id: uuid.UUID
    ) -> tuple[OrganizationMember, User]:
        membership = await self.repo.get_membership_by_id(organization_id, member_id)
        if membership is None:
            raise AppException(
                "El miembro no existe en esta empresa.",
                code="member_not_found",
                status_code=404,
            )
        user_row = await self.db.get(User, membership.user_id)
        return membership, user_row

    @staticmethod
    def _to_read(membership: OrganizationMember, user) -> MemberRead:
        return MemberRead(
            id=membership.id,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            email=user.email,
            full_name=user.full_name,
            role=membership.role,
            created_at=membership.created_at,
        )
