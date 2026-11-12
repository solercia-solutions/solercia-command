"""O5: a bootstrapped organization gets its RBAC catalog atomically.

Real PostgreSQL (SAVEPOINT ``session`` fixture): the default roles, their menu
grants and the creator's ADMIN role are written by the request-session
adapter in the SAME transaction as the organization, and vanish with it when
a later bootstrap step fails.
"""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_init import _ensure_menus
from app.modules.organizations.bootstrap import bootstrap_organization
from app.modules.organizations.bootstrap_uow import OrganizationBootstrapUow
from app.modules.organizations.models import Organization
from app.modules.organizations.schemas import OrganizationCreate
from app.modules.roles.models import Role, RoleMenu, UserRole
from app.modules.roles.seed_catalog import MENU_SEED, ROLE_MENU_SEED, ROLE_SEED
from tests.conftest import skip_no_db

pytestmark = [pytest.mark.asyncio(loop_scope="session"), skip_no_db]


async def _grants(session: AsyncSession, organization_id: uuid.UUID) -> dict[str, int]:
    result = await session.execute(
        select(Role.code, func.count(RoleMenu.id))
        .outerjoin(RoleMenu, RoleMenu.role_id == Role.id)
        .where(Role.organization_id == organization_id)
        .group_by(Role.code)
    )
    return dict(result.tuples().all())


async def test_bootstrap_creates_roles_menu_grants_and_creator_admin(
    session: AsyncSession, user
) -> None:
    creator, _ = user
    await _ensure_menus(session)
    slug = f"rbac-{uuid.uuid4().hex[:10]}"

    created = await bootstrap_organization(
        OrganizationBootstrapUow(session),
        OrganizationCreate(name="Entidad sintética", slug=slug),
        creator_id=creator.id,
        actor_id=creator.id,
    )

    grants = await _grants(session, created.id)
    assert set(grants) == {code for code, _ in ROLE_SEED}
    assert grants["ADMIN"] == len(MENU_SEED)
    assert grants["MANAGER"] == len(ROLE_MENU_SEED["MANAGER"])
    assert grants["MEMBER"] == len(ROLE_MENU_SEED["MEMBER"])
    admin_roles = await session.scalars(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(Role.organization_id == created.id, UserRole.user_id == creator.id)
    )
    assert list(admin_roles) == ["ADMIN"]


async def test_failure_after_rbac_rolls_back_roles_with_the_organization(
    session: AsyncSession, user
) -> None:
    creator, _ = user
    await _ensure_menus(session)
    slug = f"rbac-fail-{uuid.uuid4().hex[:8]}"
    roles_before = await session.scalar(select(func.count(Role.id)))
    grants_before = await session.scalar(select(func.count(UserRole.id)))
    uow = OrganizationBootstrapUow(session)

    async def boom(*_args, **_kwargs):
        raise RuntimeError("synthetic failure after RBAC")

    uow.projects.create_generales = boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="after RBAC"):
        await bootstrap_organization(
            uow,
            OrganizationCreate(name="Entidad sintética", slug=slug),
            creator_id=creator.id,
            actor_id=creator.id,
        )

    assert await session.scalar(select(Organization).where(Organization.slug == slug)) is None
    assert await session.scalar(select(func.count(Role.id))) == roles_before
    assert await session.scalar(select(func.count(UserRole.id))) == grants_before
