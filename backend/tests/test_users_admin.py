"""Tests for user administration (/admin/users).

R1 ``require_admin`` en todo ``/admin/users`` · R2 creación 201 + solo hash
bcrypt almacenado · R3 ``DELETE`` borrado suave (204, fila persiste,
desaparece del listado) · R4 ``PUT /{id}/roles`` reemplaza el set completo
de roles (openspec/specs/users-admin/spec.md).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# R1 — require_admin en todo /admin/users
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/admin/users"),
        ("POST", "/admin/users"),
    ],
)
@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_users_admin_rejects_non_admin(
    method: str, path: str, client: AsyncClient, tenant: Organization, user: tuple
) -> None:
    """A non-admin member gets 403 on the users-admin endpoints."""

    _, token = user

    response = await client.request(method, path, json={}, headers=_auth(token))

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# R2 — Creación 201 + solo hash bcrypt almacenado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_user_returns_201_and_stores_only_bcrypt_hash(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """POST /admin/users creates the user (201) and the persisted row never
    stores the plaintext password — only its bcrypt hash.
    """

    from app.modules.users.models import User

    owner, token = user
    await rbac_admin(session, tenant, owner)

    plaintext = "SuperSecreta123*"
    response = await client.post(
        "/admin/users",
        json={
            "primer_nombre": "Nueva",
            "primer_apellido": "Persona",
            "email": f"nueva-{uuid.uuid4().hex[:8]}@example.com",
            "password": plaintext,
        },
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert "password" not in body
    assert "hashed_password" not in body

    row = (
        await session.execute(select(User).where(User.id == uuid.UUID(body["id"])))
    ).scalar_one()
    assert row.hashed_password != plaintext
    assert row.hashed_password.startswith("$2b$")


# ---------------------------------------------------------------------------
# R3 — DELETE es borrado suave
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_user_is_soft_delete(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin, make_member
) -> None:
    """DELETE responds 204, the row survives with is_active=False and drops
    out of the org listing.
    """

    from app.modules.users.models import User
    from app.shared.enums import MemberRole

    owner, token = user
    await rbac_admin(session, tenant, owner)
    target_user, _ = await make_member(session, tenant, MemberRole.member)

    response = await client.delete(
        f"/admin/users/{target_user.id}", headers=_auth(token)
    )

    assert response.status_code == 204

    listing = await client.get("/admin/users", headers=_auth(token))
    listed_ids = {row["id"] for row in listing.json()["data"]}
    assert str(target_user.id) not in listed_ids

    row = (
        await session.execute(select(User).where(User.id == target_user.id))
    ).scalar_one()
    assert row.is_active is False
    assert row.deleted_at is not None


# ---------------------------------------------------------------------------
# R4 — PUT /{id}/roles reemplaza el set completo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_replace_user_roles_replaces_the_full_set(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin, make_member
) -> None:
    """PUT /{id}/roles with [C] leaves the user with ONLY role C, even
    though it previously held roles A and B.
    """

    from app.modules.roles.models import Role, UserRole
    from app.shared.enums import MemberRole

    owner, token = user
    await rbac_admin(session, tenant, owner)
    target_user, _ = await make_member(session, tenant, MemberRole.member)

    role_a = Role(organization_id=tenant.id, code="ROLE_A", name="Role A")
    role_b = Role(organization_id=tenant.id, code="ROLE_B", name="Role B")
    role_c = Role(organization_id=tenant.id, code="ROLE_C", name="Role C")
    session.add_all([role_a, role_b, role_c])
    await session.flush()
    session.add_all(
        [
            UserRole(user_id=target_user.id, role_id=role_a.id),
            UserRole(user_id=target_user.id, role_id=role_b.id),
        ]
    )
    await session.flush()

    response = await client.put(
        f"/admin/users/{target_user.id}/roles",
        json={"role_ids": [str(role_c.id)]},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    codes = {role["code"] for role in response.json()["data"]["roles"]}
    assert codes == {"ROLE_C"}
