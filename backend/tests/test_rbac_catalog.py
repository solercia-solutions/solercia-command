"""Tests for the RBAC catalog: roles, menus and dependencies (admin).

R1 ``require_admin`` en ``/admin/roles``,``/admin/menus``,``/admin/dependencies``
· R2 ``PUT /admin/roles/{id}/menus`` reemplaza grants (semántica de set) y
``GET /auth/me/menus`` refleja el cambio · R3 árbol de menús anidado por
``parent_id``/``order`` · R4 borrado suave
(openspec/specs/rbac-catalog/spec.md).

Actor autorizado vía ``rbac_admin``; actores no autorizados vía ``make_member``.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.shared.enums import MemberRole
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# R1 — require_admin protege el catálogo completo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/admin/roles"),
        ("POST", "/admin/roles"),
        ("GET", "/admin/menus"),
        ("POST", "/admin/menus"),
        ("GET", "/admin/dependencies"),
        ("POST", "/admin/dependencies"),
    ],
)
@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_catalog_endpoints_reject_non_admin(
    method: str,
    path: str,
    client: AsyncClient,
    tenant: Organization,
    user: tuple,
) -> None:
    """A member with no RBAC ADMIN role gets 403 on every catalog endpoint."""

    _, token = user

    response = await client.request(method, path, json={}, headers=_auth(token))

    assert response.status_code == 403


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_catalog_endpoint_accepts_rbac_admin(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """A user WITH the RBAC ADMIN role passes the gate (2xx, not 403)."""

    owner, token = user
    await rbac_admin(session, tenant, owner)

    response = await client.get("/admin/roles", headers=_auth(token))

    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# R2 — PUT /admin/roles/{id}/menus reemplaza el conjunto de grants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_replace_role_menus_replaces_not_appends(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """PUT with [M3] leaves the role with ONLY M3, even though it had M1+M2."""

    from app.modules.menus.models import Menu
    from app.modules.roles.models import Role, RoleMenu, UserRole

    owner, token = user
    await rbac_admin(session, tenant, owner)

    m1, m2, m3 = Menu(name="M1"), Menu(name="M2"), Menu(name="M3")
    session.add_all([m1, m2, m3])
    await session.flush()

    role = Role(organization_id=tenant.id, code="EDITOR", name="Editor")
    session.add(role)
    await session.flush()
    session.add_all(
        [
            RoleMenu(role_id=role.id, menu_id=m1.id),
            RoleMenu(role_id=role.id, menu_id=m2.id),
        ]
    )
    await session.flush()

    # Grant the role to a second user so we can assert GET /auth/me/menus
    # reflects the change end-to-end.
    import uuid

    from app.modules.organizations.models import OrganizationMember
    from app.modules.users.models import User
    from app.shared.security import create_access_token, hash_password

    grantee = User(
        email=f"grantee-{uuid.uuid4().hex[:12]}@example.com",
        primer_nombre="Grantee",
        primer_apellido="User",
        hashed_password=hash_password("Test123*"),
    )
    session.add(grantee)
    await session.flush()
    session.add(
        OrganizationMember(
            organization_id=tenant.id, user_id=grantee.id, role=MemberRole.member
        )
    )
    session.add(UserRole(user_id=grantee.id, role_id=role.id))
    await session.flush()
    grantee_token = create_access_token(str(grantee.id))

    response = await client.put(
        f"/admin/roles/{role.id}/menus",
        json={"menu_ids": [str(m3.id)]},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert set(response.json()["data"]["menu_ids"]) == {str(m3.id)}

    menus_response = await client.get(
        "/auth/me/menus", headers=_auth(grantee_token)
    )
    assert menus_response.status_code == 200, menus_response.text
    names = {node["name"] for node in menus_response.json()}
    assert names == {"M3"}


# ---------------------------------------------------------------------------
# R3 — Árbol de menús anidado por parent_id/order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_menu_tree_nests_children_ordered(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """``meta.tree`` from GET /admin/menus nests children under their parent,
    ordered by ``order`` then ``name``.
    """

    from app.modules.menus.models import Menu

    owner, token = user
    await rbac_admin(session, tenant, owner)

    parent = Menu(name="Parent", order=0)
    session.add(parent)
    await session.flush()

    child_b = Menu(name="Child B", parent_id=parent.id, order=2)
    child_a = Menu(name="Child A", parent_id=parent.id, order=1)
    session.add_all([child_b, child_a])
    await session.flush()

    response = await client.get("/admin/menus", headers=_auth(token))

    assert response.status_code == 200, response.text
    tree = response.json()["meta"]["tree"]
    parent_node = next(node for node in tree if node["name"] == "Parent")
    child_names_in_order = [child["name"] for child in parent_node["children"]]
    assert child_names_in_order == ["Child A", "Child B"]


# ---------------------------------------------------------------------------
# R4 — Borrado suave del catálogo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_role_is_soft_delete(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """DELETE /admin/roles/{id} responds 204, the row persists but is inactive
    and no longer appears in the listing.
    """

    from sqlalchemy import select

    from app.modules.roles.models import Role

    owner, token = user
    await rbac_admin(session, tenant, owner)

    role = Role(organization_id=tenant.id, code="TEMP", name="Temp Role")
    session.add(role)
    await session.flush()
    role_id = role.id

    response = await client.delete(f"/admin/roles/{role_id}", headers=_auth(token))

    assert response.status_code == 204

    listing = await client.get("/admin/roles", headers=_auth(token))
    listed_ids = {row["id"] for row in listing.json()["data"]}
    assert str(role_id) not in listed_ids

    row = (
        await session.execute(select(Role).where(Role.id == role_id))
    ).scalar_one()
    assert row.is_active is False
    assert row.deleted_at is not None
