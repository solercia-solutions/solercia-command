"""Atomic new-tenant bootstrap; no existing-tenant repair or backfill."""
from typing import Protocol
from uuid import UUID

from app.modules.organizations.schemas import OrganizationCreate, OrganizationRead
from app.modules.projects.system_project_ports import SystemProjectPort
from app.modules.projects.system_project_provisioning import ensure_generales
from app.shared.exceptions import AppException


class OrganizationBootstrapPort(Protocol):
    async def slug_exists(self, slug: str) -> bool: ...

    async def create_with_admin(
        self, data: OrganizationCreate, *, creator_id: UUID, actor_id: UUID | None,
    ) -> OrganizationRead:
        """Flush both new rows in the caller's transaction before returning."""
        ...


class RbacProvisioningPort(Protocol):
    async def provision_default_roles(
        self, organization_id: UUID, *, admin_user_id: UUID, actor_id: UUID | None,
    ) -> None:
        """Create the seed roles, their menu grants and the creator's ADMIN role.

        Flushes in the caller's transaction; never commits.
        """
        ...


class BootstrapUow(Protocol):
    organizations: OrganizationBootstrapPort
    rbac: RbacProvisioningPort
    projects: SystemProjectPort

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


async def bootstrap_organization(
    uow: BootstrapUow, data: OrganizationCreate, *,
    creator_id: UUID, actor_id: UUID | None,
) -> OrganizationRead:
    """Complete once, including an auth-autobegun transaction on the same session.

    The caller owns the session lifecycle; this use case owns its completion.
    Root placement is intentional ONLY for this newly created, empty tenant.
    """
    try:
        if await uow.organizations.slug_exists(data.slug):
            raise AppException(
                "Ya existe una empresa con ese identificador (slug).",
                code="organization_slug_taken", status_code=409,
            )
        organization = await uow.organizations.create_with_admin(
            data, creator_id=creator_id, actor_id=actor_id,
        )
        # Without its roles the creator would see an empty menu (O5).
        await uow.rbac.provision_default_roles(
            organization.id, admin_user_id=creator_id, actor_id=actor_id,
        )
        await ensure_generales(
            uow.projects, organization_id=organization.id,
            actor_id=actor_id, parent_id=None,
        )
        await uow.commit()
        return organization
    except BaseException:
        # Includes failed flush/commit and cancellation; never return partial data.
        await uow.rollback()
        raise
