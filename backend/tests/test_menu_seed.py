"""Focused test for the `/hierarchy` menu row (24-hierarchy-tree-view, R1 fix).

Without a menu-nav row, the hierarchy view is only reachable via the static
`fallbackLinks()` — which a normal org never uses once its menu tree loads
(`useMenuNav()` becomes true). This test proves the backend seed exposes the
route through the DB-driven menu instead.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_init import _ensure_menus, _ensure_role_menus, _ensure_roles
from app.modules.menus.models import Menu
from app.modules.organizations.models import Organization
from app.modules.roles.models import RoleMenu
from tests.conftest import skip_no_db


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_menu_seed_exposes_hierarchy_route_to_a_projects_role(
    session: AsyncSession,
    tenant: Organization,
) -> None:
    roles = await _ensure_roles(session, tenant)
    menus = await _ensure_menus(session)
    await _ensure_role_menus(session, roles, menus)
    await session.flush()

    hierarchy_menu = menus.get("Jerarquía")
    assert hierarchy_menu is not None
    assert hierarchy_menu.path == "/hierarchy"

    # Every role that also sees "Proyectos" must be granted "Jerarquía" too
    # (ADMIN's "*" grant already covers it).
    projects_menu = menus["Proyectos"]
    for code, role in roles.items():
        has_projects = (
            await session.execute(
                select(RoleMenu).where(
                    RoleMenu.role_id == role.id,
                    RoleMenu.menu_id == projects_menu.id,
                )
            )
        ).scalar_one_or_none()
        if has_projects is None:
            continue
        has_hierarchy = (
            await session.execute(
                select(RoleMenu).where(
                    RoleMenu.role_id == role.id,
                    RoleMenu.menu_id == hierarchy_menu.id,
                )
            )
        ).scalar_one_or_none()
        assert has_hierarchy is not None, (
            f"role {code} sees Proyectos but not Jerarquía"
        )

    # Idempotency: re-running the seed does not duplicate the row.
    result = await session.execute(select(Menu).where(Menu.path == "/hierarchy"))
    assert len(result.scalars().all()) == 1
