"""Tests for organizations-admin CRUD: bootstrap, read, update, soft delete.

organizations-admin R1 (bootstrap deja al creador como admin) · R2 (permisos
por rol en lectura/escritura). Any authenticated user may create an
organization and becomes its sole ``admin`` in the same commit; any member
may read it (404 if not a member); only an ``admin`` of THAT organization
may update or soft-delete it (403 if member, 404 if not a member at all).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 3.1-3.3 — POST /organizations (bootstrap)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_organization_bootstraps_creator_as_admin(
    client: AsyncClient, user
) -> None:
    """Creation succeeds and the creator is `admin` of the new organization."""

    _, token = user

    response = await client.post(
        "/organizations",
        json={"name": "Nueva Empresa", "slug": "nueva-empresa-bootstrap"},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["name"] == "Nueva Empresa"
    assert body["slug"] == "nueva-empresa-bootstrap"
    assert body["is_active"] is True

    mine_response = await client.get("/organizations/mine", headers=_auth(token))
    roles_by_slug = {
        row["organization"]["slug"]: row["role"] for row in mine_response.json()["data"]
    }
    assert roles_by_slug["nueva-empresa-bootstrap"] == "admin"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_organization_duplicate_slug_is_rejected(
    client: AsyncClient, user, tenant
) -> None:
    """A duplicate slug is rejected and no new organization is created."""

    _, token = user

    response = await client.post(
        "/organizations",
        json={"name": "Otra Empresa", "slug": tenant.slug},
        headers=_auth(token),
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "organization_slug_taken"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_organization_requires_auth(client: AsyncClient) -> None:
    """No token -> 401."""

    response = await client.post(
        "/organizations", json={"name": "Sin Auth", "slug": "sin-auth-org"}
    )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 3.4-3.5 — GET /organizations/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_organization_any_member_can_read(
    client: AsyncClient, two_orgs: TwoOrgs, session: AsyncSession, make_member
) -> None:
    """Any member (admin or plain member) can read their own organization."""

    from app.shared.enums import MemberRole

    _, member_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )

    response = await client.get(
        f"/organizations/{two_orgs.a.organization.id}", headers=_auth(member_token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["id"] == str(two_orgs.a.organization.id)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_organization_non_member_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A non-member gets 404, never revealing whether the org exists."""

    response = await client.get(
        f"/organizations/{two_orgs.b.organization.id}",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_organization_requires_auth(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """No token -> 401."""

    response = await client.get(f"/organizations/{two_orgs.a.organization.id}")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 3.6-3.7 — PATCH /organizations/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_organization_as_admin_persists_name(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """An admin of the organization can update its name."""

    response = await client.patch(
        f"/organizations/{two_orgs.a.organization.id}",
        json={"name": "Org A Renombrada"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["name"] == "Org A Renombrada"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_organization_rejected_for_member_role(
    client: AsyncClient, two_orgs: TwoOrgs, session: AsyncSession, make_member
) -> None:
    """A plain member gets 403; the organization stays unchanged."""

    from app.shared.enums import MemberRole

    _, member_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )

    response = await client.patch(
        f"/organizations/{two_orgs.a.organization.id}",
        json={"name": "No Debería Cambiar"},
        headers=_auth(member_token),
    )

    assert response.status_code == 403, response.text

    await session.refresh(two_orgs.a.organization)
    assert two_orgs.a.organization.name == "Org A"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_organization_non_member_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A non-member trying to PATCH gets 404, not 403."""

    response = await client.patch(
        f"/organizations/{two_orgs.b.organization.id}",
        json={"name": "Intento Ajeno"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 3.8-3.9 — DELETE /organizations/{id} (soft delete)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_organization_as_admin_soft_deletes(
    client: AsyncClient, two_orgs: TwoOrgs, session: AsyncSession
) -> None:
    """DELETE deactivates the organization (soft delete), never a hard delete."""

    response = await client.delete(
        f"/organizations/{two_orgs.a.organization.id}",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 200, response.text

    await session.refresh(two_orgs.a.organization)
    assert two_orgs.a.organization.is_active is False


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_organization_rejected_for_member_role(
    client: AsyncClient, two_orgs: TwoOrgs, session: AsyncSession, make_member
) -> None:
    """A plain member gets 403 on DELETE; the organization stays active."""

    from app.shared.enums import MemberRole

    _, member_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )

    response = await client.delete(
        f"/organizations/{two_orgs.a.organization.id}", headers=_auth(member_token)
    )

    assert response.status_code == 403, response.text

    await session.refresh(two_orgs.a.organization)
    assert two_orgs.a.organization.is_active is True


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_organization_non_member_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A non-member trying to DELETE gets 404, not 403."""

    response = await client.delete(
        f"/organizations/{two_orgs.b.organization.id}",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404
