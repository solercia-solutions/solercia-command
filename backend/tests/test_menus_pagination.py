"""Pagination tests for ``GET /admin/menus`` (R1, G1).

Menus are a GLOBAL catalog: ``meta.tree`` is always built from the FULL
active set, never from the paginated ``data`` slice — this is gate #1 from
design.md ("Correcciones de gate"), verified explicitly below with and
without pagination params.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.menus.models import Menu
from app.modules.organizations.models import Organization
from app.modules.roles.models import Role, UserRole
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _grant_admin(session: AsyncSession, tenant: Organization, user: User) -> None:
    role = Role(organization_id=tenant.id, code="ADMIN", name="Administrator")
    session.add(role)
    await session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.flush()


async def _seed_menus(session: AsyncSession, names: list[str]) -> None:
    for index, name in enumerate(names):
        session.add(
            Menu(name=name, path=f"/{uuid.uuid4().hex[:8]}", order=index)
        )
    await session.flush()


def _tree_names(tree: list[dict]) -> list[str]:
    return [node["name"] for node in tree]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_menus_without_params_is_byte_compatible_and_has_tree(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    caller, token = user
    await _grant_admin(session, tenant, caller)
    await _seed_menus(session, ["Menu A", "Menu B", "Menu C"])

    response = await client.get("/admin/menus", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 3
    assert body["meta"]["total"] == 3
    assert "page" not in body["meta"]
    assert "size" not in body["meta"]
    assert _tree_names(body["meta"]["tree"]) == ["Menu A", "Menu B", "Menu C"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_menus_page_and_size_slices_data_but_tree_stays_whole(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Gate #1: ``data`` is sliced by pagination, ``meta.tree`` never is."""

    caller, token = user
    await _grant_admin(session, tenant, caller)
    await _seed_menus(session, ["Menu A", "Menu B", "Menu C", "Menu D", "Menu E"])

    response = await client.get(
        "/admin/menus",
        params={"page": 2, "size": 2, "sort": "name", "order": "asc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert [m["name"] for m in body["data"]] == ["Menu C", "Menu D"]
    assert body["meta"]["page"] == 2
    assert body["meta"]["size"] == 2
    assert body["meta"]["total"] == 5
    # The tree ALWAYS reflects the full active set, regardless of the slice.
    assert _tree_names(body["meta"]["tree"]) == [
        "Menu A",
        "Menu B",
        "Menu C",
        "Menu D",
        "Menu E",
    ]
