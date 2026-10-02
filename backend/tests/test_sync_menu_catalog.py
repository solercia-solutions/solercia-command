"""``scripts.sync_menu_catalog`` on real PostgreSQL (change 45c).

Insert-only and idempotent: missing global menus and missing ``role_menus`` per
organization are inserted; existing rows are never updated or deleted; a dry
run writes nothing. Assertions are scoped to the test's own organization
because the test database is shared with other committed fixtures.
"""

import os
import uuid

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.menus.models import Menu
from app.modules.organizations.models import Organization
from app.modules.roles.models import Role, RoleMenu
from app.modules.roles.seed_catalog import MENU_SEED, ROLE_MENU_SEED
from scripts.sync_menu_catalog import (
    EXIT_OK,
    EXIT_USAGE_ERROR,
    build_parser,
    main,
    run,
    sync_catalog,
)
from tests.conftest import skip_no_db

pytestmark = [pytest.mark.asyncio(loop_scope="session"), skip_no_db]


async def _roles(session: AsyncSession, organization: Organization) -> dict[str, Role]:
    roles = {}
    for code in ROLE_MENU_SEED:
        role = Role(organization_id=organization.id, code=code, name=code.title())
        session.add(role)
        roles[code] = role
    await session.flush()
    return roles


async def _granted(session: AsyncSession, role: Role) -> set[str]:
    rows = await session.execute(
        select(Menu.name)
        .join(RoleMenu, RoleMenu.menu_id == Menu.id)
        .where(RoleMenu.role_id == role.id)
    )
    return set(rows.scalars())


def _expected(code: str) -> set[str]:
    spec = ROLE_MENU_SEED[code]
    return {row[0] for row in MENU_SEED} if spec == "*" else set(spec)


async def test_apply_inserts_missing_grants_and_is_idempotent(session: AsyncSession, tenant):
    roles = await _roles(session, tenant)

    first = await sync_catalog(session, apply=True)

    mine = [g for g in first.missing_grants if g[0] == tenant.slug]
    assert len(mine) == sum(len(_expected(code)) for code in ROLE_MENU_SEED)
    for code, role in roles.items():
        assert await _granted(session, role) == _expected(code)
    assert (await session.scalar(select(func.count(Menu.id)).where(Menu.name == "Planes"))) == 1

    second = await sync_catalog(session, apply=True)

    assert second.missing_menus == []
    assert [g for g in second.missing_grants if g[0] == tenant.slug] == []


async def test_apply_never_updates_or_deletes_existing_rows(session: AsyncSession, tenant):
    roles = await _roles(session, tenant)
    await sync_catalog(session, apply=True)
    planes = await session.scalar(select(Menu).where(Menu.name == "Planes"))
    planes.icon = "icono-local"
    extra = Menu(name=f"Extra {uuid.uuid4().hex[:6]}", icon="x", path="/x", order=99)
    session.add(extra)
    await session.flush()
    session.add(RoleMenu(role_id=roles["MEMBER"].id, menu_id=extra.id))
    await session.execute(
        delete(RoleMenu).where(
            RoleMenu.role_id == roles["MEMBER"].id, RoleMenu.menu_id == planes.id
        )
    )
    await session.flush()

    result = await sync_catalog(session, apply=True)

    assert [g for g in result.missing_grants if g[0] == tenant.slug] == [
        (tenant.slug, "MEMBER", "Planes")
    ]
    await session.refresh(planes)
    assert planes.icon == "icono-local"  # never updated
    assert await _granted(session, roles["MEMBER"]) == _expected("MEMBER") | {extra.name}


async def test_org_without_roles_is_reported_not_created(session: AsyncSession, tenant):
    result = await sync_catalog(session, apply=True)

    assert f"{tenant.slug}: sin rol ADMIN; no se crea ni se otorga." in result.notes
    count = await session.scalar(
        select(func.count(Role.id)).where(Role.organization_id == tenant.id)
    )
    assert count == 0


async def test_cli_dry_run_writes_nothing(engine: AsyncEngine, capsys):
    slug = f"menu-sync-{uuid.uuid4().hex[:10]}"
    async with engine.begin() as connection:
        org_id = await connection.scalar(
            insert(Organization)
            .values(name="Entidad sintética", slug=slug)
            .returning(Organization.id)
        )
        await connection.execute(
            insert(Role).values(organization_id=org_id, code="MEMBER", name="Colaborador")
        )
    args = build_parser().parse_args(["--database-url", os.environ["TEST_DATABASE_URL"]])

    assert await run(args) == EXIT_OK

    out = capsys.readouterr().out
    assert "Modo: simulación (solo lectura)" in out
    assert f"+ {slug} · MEMBER → «Planes»" in out
    async with AsyncSession(engine) as reader:
        grants = await reader.scalar(
            select(func.count(RoleMenu.id))
            .join(Role, Role.id == RoleMenu.role_id)
            .where(Role.organization_id == org_id)
        )
        assert grants == 0


def test_database_url_is_required():
    assert main([]) == EXIT_USAGE_ERROR
