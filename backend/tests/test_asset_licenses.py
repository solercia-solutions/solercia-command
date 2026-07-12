"""Tests for asset licences — nested CRUD + delete propagation (change 07).

R4 Licencias anidadas CRUD + propagación de borrado ·
R6 Aislamiento multi-tenant (specs/assets/spec.md). Escrituras exigen RBAC
admin vía la fixture ``rbac_admin``.
"""

import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_asset(session: AsyncSession, tenant: Organization, *, name: str = "Suite Office"):
    from app.modules.assets.models import Asset

    asset = Asset(organization_id=tenant.id, name=name, asset_type="saas_subscription")
    session.add(asset)
    await session.flush()
    return asset


async def _seed_license(
    session: AsyncSession,
    asset,
    *,
    organization_id,
    start_date: date | None = None,
    expiration_date: date | None = None,
):
    from app.modules.assets.models import AssetLicense

    license_row = AssetLicense(
        organization_id=organization_id,
        asset_id=asset.id,
        license_type="subscription",
        start_date=start_date or date.today(),
        expiration_date=expiration_date or (date.today() + timedelta(days=365)),
    )
    session.add(license_row)
    await session.flush()
    return license_row


# ---------------------------------------------------------------------------
# R4 — Creación válida
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_license_with_valid_dates_returns_201(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """POST /assets/{id}/licenses creates the licence when expiration > start."""

    owner, token = user
    await rbac_admin(session, tenant, owner)
    asset = await _seed_asset(session, tenant)

    response = await client.post(
        f"/assets/{asset.id}/licenses",
        json={
            "license_type": "subscription",
            "start_date": "2026-01-01",
            "expiration_date": "2027-01-01",
        },
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["asset_id"] == str(asset.id)
    assert body["license_type"] == "subscription"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_license_with_invalid_dates_returns_422(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """expiration_date <= start_date is rejected with 422."""

    owner, token = user
    await rbac_admin(session, tenant, owner)
    asset = await _seed_asset(session, tenant)

    response = await client.post(
        f"/assets/{asset.id}/licenses",
        json={
            "license_type": "subscription",
            "start_date": "2026-01-01",
            "expiration_date": "2026-01-01",
        },
        headers=_auth(token),
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# R4 — Edición y borrado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_license_by_admin(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """PATCH /asset-licenses/{id} edits seats/auto_renew."""

    owner, token = user
    await rbac_admin(session, tenant, owner)
    asset = await _seed_asset(session, tenant)
    license_row = await _seed_license(session, asset, organization_id=tenant.id)

    response = await client.patch(
        f"/asset-licenses/{license_row.id}",
        json={"seats": 25, "auto_renew": True},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["seats"] == 25
    assert body["auto_renew"] is True


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_license_is_soft_delete(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """DELETE /asset-licenses/{id} responds 204 and the licence leaves GET .../licenses."""

    owner, token = user
    await rbac_admin(session, tenant, owner)
    asset = await _seed_asset(session, tenant)
    license_row = await _seed_license(session, asset, organization_id=tenant.id)

    response = await client.delete(
        f"/asset-licenses/{license_row.id}", headers=_auth(token)
    )
    assert response.status_code == 204

    listing = await client.get(f"/assets/{asset.id}/licenses", headers=_auth(token))
    listed_ids = {row["id"] for row in listing.json()["data"]}
    assert str(license_row.id) not in listed_ids


# ---------------------------------------------------------------------------
# R4 — Licencias inaccesibles tras el borrado soft del activo padre
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_licenses_become_inaccessible_after_parent_asset_soft_delete(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """Soft-deleting the parent asset propagates: licences 404 on GET/PATCH/DELETE."""

    owner, token = user
    await rbac_admin(session, tenant, owner)
    asset = await _seed_asset(session, tenant)
    license_row = await _seed_license(session, asset, organization_id=tenant.id)

    delete_asset_response = await client.delete(f"/assets/{asset.id}", headers=_auth(token))
    assert delete_asset_response.status_code == 204

    list_response = await client.get(f"/assets/{asset.id}/licenses", headers=_auth(token))
    assert list_response.status_code == 404

    patch_response = await client.patch(
        f"/asset-licenses/{license_row.id}", json={"seats": 5}, headers=_auth(token)
    )
    assert patch_response.status_code == 404

    delete_license_response = await client.delete(
        f"/asset-licenses/{license_row.id}", headers=_auth(token)
    )
    assert delete_license_response.status_code == 404


# ---------------------------------------------------------------------------
# R6 — Aislamiento multi-tenant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_license_of_another_org_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """GET/PATCH/DELETE on a licence of org B's asset, with org A's admin token, is 404."""

    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)
    asset_b = await _seed_asset(session, two_orgs.b.organization, name="Activo B")
    license_b = await _seed_license(
        session, asset_b, organization_id=two_orgs.b.organization.id
    )

    patch_response = await client.patch(
        f"/asset-licenses/{license_b.id}",
        json={"seats": 3},
        headers=_auth(two_orgs.a.token),
    )
    delete_response = await client.delete(
        f"/asset-licenses/{license_b.id}", headers=_auth(two_orgs.a.token)
    )

    assert patch_response.status_code == 404
    assert delete_response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_random_license_id_returns_404(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """A random license id that does not exist returns 404, never a 500."""

    owner, token = user
    await rbac_admin(session, tenant, owner)

    response = await client.patch(
        f"/asset-licenses/{uuid.uuid4()}", json={"seats": 1}, headers=_auth(token)
    )

    assert response.status_code == 404
