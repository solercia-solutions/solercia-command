"""Request-session adapter for atomic organization bootstrap.

Deployment prerequisite: migration 0026 must be applied before enabling this
path. It has NOT been applied operationally by this change. No startup/backfill
hook is installed here. The injected session may already have autobegun during
authentication; never begin/nest/replace it or close this caller-owned session.
"""
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.menus.models import Menu
from app.modules.organizations.models import Organization
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import OrganizationCreate, OrganizationRead
from app.modules.projects.system_project_repository import SystemProjectRepository
from app.modules.roles.models import Role, RoleMenu, UserRole
from app.modules.roles.seed_catalog import (
    ADMIN_ROLE_CODE,
    MENU_SEED,
    ROLE_MENU_SEED,
    ROLE_SEED,
)
from app.shared.exceptions import AppException


class BootstrapOrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = OrganizationRepository(session)

    async def slug_exists(self, slug: str) -> bool:
        return await self.repository.get_by_slug(slug) is not None

    async def create_with_admin(
        self, data: OrganizationCreate, *, creator_id: UUID, actor_id: UUID | None,
    ) -> OrganizationRead:
        try:
            organization = await self.repository.create_with_admin(
                Organization(name=data.name, slug=data.slug,
                             created_by=actor_id, updated_by=actor_id),
                creator_id=creator_id,
            )
        except IntegrityError as exc:
            name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if name is None:
                name = getattr(getattr(exc.orig, "__cause__", None), "constraint_name", None)
            if name == "ix_organizations_slug":
                raise AppException(
                    "Ya existe una empresa con ese identificador (slug).",
                    code="organization_slug_taken", status_code=409,
                ) from exc
            raise
        # Build response before completion; no post-commit refresh can fail after
        # making partial success externally visible, even with expiring sessions.
        return OrganizationRead.model_validate(organization)


class BootstrapRbacRepository:
    """Seed RBAC catalog for a NEW organization, in the caller's transaction.

    Same catalog as the startup seed (``app.modules.roles.seed_catalog``).
    Menus are global and created by that startup seed; here they are only
    granted, never created, so a tenant bootstrap does not write global rows.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def provision_default_roles(
        self, organization_id: UUID, *, admin_user_id: UUID, actor_id: UUID | None,
    ) -> None:
        roles = {
            code: Role(id=uuid4(), organization_id=organization_id, code=code, name=name,
                       created_by=actor_id, updated_by=actor_id)
            for code, name in ROLE_SEED
        }
        self.session.add_all(roles.values())
        names = [name for name, *_ in MENU_SEED]
        result = await self.session.execute(
            select(Menu.name, Menu.id).where(Menu.name.in_(names), Menu.is_active.is_(True))
        )
        menus = dict(result.tuples().all())
        for code, spec in ROLE_MENU_SEED.items():
            granted = names if spec == "*" else spec
            self.session.add_all(
                RoleMenu(role_id=roles[code].id, menu_id=menus[name])
                for name in granted if name in menus
            )
        self.session.add(UserRole(user_id=admin_user_id, role_id=roles[ADMIN_ROLE_CODE].id))
        await self.session.flush()


class OrganizationBootstrapUow:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.organizations = BootstrapOrganizationRepository(session)
        self.rbac = BootstrapRbacRepository(session)
        self.projects = SystemProjectRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
