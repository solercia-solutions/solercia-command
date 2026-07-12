"""Pagination tests for ``GET /admin/users`` and ``GET /admin/roles`` (R1, R2, R3).

Both endpoints require an administrator (``require_admin``), so every test
grants the caller (the shared ``user`` fixture) an ``ADMIN`` RBAC role before
exercising the four pagination scenarios from ``specs/api-pagination.md``.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.roles.models import Role, UserRole
from app.modules.users.models import User
from app.shared.enums import MemberRole
from app.shared.security import hash_password
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _grant_admin(session: AsyncSession, tenant: Organization, user: User) -> None:
    role = Role(organization_id=tenant.id, code="ADMIN", name="Administrator")
    session.add(role)
    await session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.flush()


async def _seed_users(
    session: AsyncSession, tenant: Organization, primer_nombres: list[str]
) -> None:
    for nombre in primer_nombres:
        member = User(
            email=f"pagination-{uuid.uuid4().hex[:12]}@example.com",
            primer_nombre=nombre,
            primer_apellido="Seed",
            hashed_password=hash_password("Test123*"),
        )
        session.add(member)
        await session.flush()
        session.add(
            OrganizationMember(
                organization_id=tenant.id, user_id=member.id, role=MemberRole.member
            )
        )
    await session.flush()


async def _seed_roles(
    session: AsyncSession, tenant: Organization, names: list[str]
) -> None:
    for name in names:
        session.add(
            Role(
                organization_id=tenant.id,
                code=name[:3].upper() + uuid.uuid4().hex[:4].upper(),
                name=name,
            )
        )
    await session.flush()


# ---------------------------------------------------------------------------
# GET /admin/users
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_users_without_params_is_byte_compatible(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    caller, token = user
    await _grant_admin(session, tenant, caller)
    await _seed_users(session, tenant, ["Ana01", "Bea02"])

    response = await client.get("/admin/users", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 3  # caller + 2 seeded
    assert body["meta"] == {"total": 3}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_users_page_and_size_returns_correct_slice(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    caller, token = user
    await _grant_admin(session, tenant, caller)
    # Caller's primer_nombre is "Test" (conftest fixture) — sorts last.
    await _seed_users(session, tenant, ["Ana01", "Bea02", "Cleo03", "Dora04"])

    response = await client.get(
        "/admin/users",
        params={"page": 2, "size": 2, "sort": "primer_nombre", "order": "asc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 2, "size": 2, "total": 5}
    assert [u["primer_nombre"] for u in body["data"]] == ["Cleo03", "Dora04"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_users_sort_outside_whitelist_is_422(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    caller, token = user
    await _grant_admin(session, tenant, caller)

    response = await client.get(
        "/admin/users", params={"sort": "hashed_password"}, headers=_auth(token)
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_sort_field"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_users_sort_primer_nombre_desc_orders_results(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    caller, token = user
    await _grant_admin(session, tenant, caller)
    await _seed_users(session, tenant, ["Ana01", "Bea02"])

    response = await client.get(
        "/admin/users",
        params={"sort": "primer_nombre", "order": "desc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    # Caller's primer_nombre "Test" sorts before "Bea02"/"Ana01" in descending order.
    assert [u["primer_nombre"] for u in response.json()["data"]] == [
        "Test",
        "Bea02",
        "Ana01",
    ]


# ---------------------------------------------------------------------------
# GET /admin/roles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_roles_without_params_is_byte_compatible(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    caller, token = user
    await _grant_admin(session, tenant, caller)  # creates the "Administrator" role

    response = await client.get("/admin/roles", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 1
    assert body["meta"] == {"total": 1}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_roles_page_and_size_returns_correct_slice(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    caller, token = user
    await _grant_admin(session, tenant, caller)  # "Administrator" — sorts first
    await _seed_roles(session, tenant, ["Bravo", "Charlie", "Delta", "Echo"])

    response = await client.get(
        "/admin/roles",
        params={"page": 2, "size": 2, "sort": "name", "order": "asc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 2, "size": 2, "total": 5}
    assert [r["name"] for r in body["data"]] == ["Charlie", "Delta"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_roles_sort_outside_whitelist_is_422(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    caller, token = user
    await _grant_admin(session, tenant, caller)

    response = await client.get(
        "/admin/roles", params={"sort": "organization_id"}, headers=_auth(token)
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_sort_field"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_roles_sort_name_desc_orders_results(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    caller, token = user
    await _grant_admin(session, tenant, caller)  # "Administrator"
    await _seed_roles(session, tenant, ["Bravo", "Charlie"])

    response = await client.get(
        "/admin/roles",
        params={"sort": "name", "order": "desc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert [r["name"] for r in response.json()["data"]] == [
        "Charlie",
        "Bravo",
        "Administrator",
    ]
