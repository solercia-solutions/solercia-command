"""Tests for the per-organization theme endpoints (feat/org-theme).

Contract:
- ``GET /organizations/me/theme`` — any authenticated member reads the
  ThemeFile of THEIR organization (``{"data": null}`` when unset). The UI
  bootstrap needs this, so no admin gate on reads.
- ``PUT /organizations/me/theme`` — RBAC ``ADMIN`` only. Body must be a JSON
  object (the ThemeFile); any non-object payload is rejected with 422.
  Stamps ``organizations.updated_by`` with the actor.
- ``DELETE /organizations/me/theme`` — RBAC ``ADMIN`` only. Resets the theme
  to ``null`` (default bundled theme).

Tenant scope is ALWAYS resolved from the JWT membership (never from a URL
id), so cross-tenant reads/writes are impossible by construction — still
asserted here via the ``two_orgs`` pattern.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# Minimal ThemeFile-shaped payload (the API stores it opaquely; the full
# schema is validated client-side by @solercia/ui's isRenderableTheme).
_THEME = {
    "meta": {"tenant": "org-a", "logo": {"url": "", "altText": "Org A", "width": 120}},
    "primitives": {"color": {"brand": {"600": "#7C3AED"}}},
    "modes": {
        "light": {"semantic": {"color": {"primary": "#7C3AED"}}},
        "dark": {"semantic": {"color": {"primary": "#8B5CF6"}}},
    },
}


# ---------------------------------------------------------------------------
# GET — lectura por cualquier miembro
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_theme_returns_null_when_unset(
    client: AsyncClient, user
) -> None:
    """GET /organizations/me/theme with no stored theme returns data=null."""

    _, token = user
    response = await client.get("/organizations/me/theme", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert response.json()["data"] is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_theme_requires_auth(client: AsyncClient) -> None:
    """GET /organizations/me/theme without a token returns 401."""

    response = await client.get("/organizations/me/theme")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# PUT — solo ADMIN (RBAC), persiste y sella updated_by
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_theme_as_admin_persists_and_get_returns_it(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """PUT stores the ThemeFile and a later GET returns the same object."""

    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)

    put_response = await client.put(
        "/organizations/me/theme", json=_THEME, headers=_auth(two_orgs.a.token)
    )
    assert put_response.status_code == 200, put_response.text
    body = put_response.json()
    assert body["data"] == _THEME
    assert "message" in body

    get_response = await client.get(
        "/organizations/me/theme", headers=_auth(two_orgs.a.token)
    )
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["data"] == _THEME


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_theme_stamps_updated_by(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """PUT seals organizations.updated_by with the authenticated actor."""

    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)

    response = await client.put(
        "/organizations/me/theme", json=_THEME, headers=_auth(two_orgs.a.token)
    )
    assert response.status_code == 200, response.text

    await session.refresh(two_orgs.a.organization)
    assert two_orgs.a.organization.updated_by == two_orgs.a.user.id
    assert two_orgs.a.organization.theme == _THEME


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_theme_rejected_for_member(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """A plain member (no RBAC ADMIN role) gets 403 on PUT."""

    from app.shared.enums import MemberRole

    _, member_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )

    response = await client.put(
        "/organizations/me/theme", json=_THEME, headers=_auth(member_token)
    )

    assert response.status_code == 403, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_theme_non_object_body_returns_422(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """PUT with a non-object JSON body (list / string) is rejected with 422."""

    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)

    for bad_body in (["not", "an", "object"], "plain-string", 42):
        response = await client.put(
            "/organizations/me/theme", json=bad_body, headers=_auth(two_orgs.a.token)
        )
        assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# DELETE — solo ADMIN, vuelve al tema por defecto (null)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_theme_resets_to_null(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """DELETE clears the stored theme; a later GET returns data=null."""

    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)

    put_response = await client.put(
        "/organizations/me/theme", json=_THEME, headers=_auth(two_orgs.a.token)
    )
    assert put_response.status_code == 200, put_response.text

    delete_response = await client.delete(
        "/organizations/me/theme", headers=_auth(two_orgs.a.token)
    )
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json()["data"] is None

    get_response = await client.get(
        "/organizations/me/theme", headers=_auth(two_orgs.a.token)
    )
    assert get_response.json()["data"] is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_theme_rejected_for_member(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """A plain member (no RBAC ADMIN role) gets 403 on DELETE."""

    from app.shared.enums import MemberRole

    _, member_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )

    response = await client.delete(
        "/organizations/me/theme", headers=_auth(member_token)
    )

    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# Aislamiento multi-tenant (two_orgs)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_theme_is_isolated_between_orgs(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """Org A stores a theme; org B still reads data=null (and vice versa)."""

    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)

    put_response = await client.put(
        "/organizations/me/theme", json=_THEME, headers=_auth(two_orgs.a.token)
    )
    assert put_response.status_code == 200, put_response.text

    response_b = await client.get(
        "/organizations/me/theme", headers=_auth(two_orgs.b.token)
    )
    assert response_b.status_code == 200, response_b.text
    assert response_b.json()["data"] is None

    response_a = await client.get(
        "/organizations/me/theme", headers=_auth(two_orgs.a.token)
    )
    assert response_a.json()["data"] == _THEME
