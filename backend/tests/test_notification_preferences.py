"""Tests for GET/PUT /notification-preferences (change 08, Fase C).

R4 Preferencia de digest por usuario · R7 CRUD de preferencias · R8
Aislamiento multi-tenant (specs/email-notifications/spec.md).

Uses the in-process ``client`` fixture (never the live-server black-box
tests) — mirrors ``test_notifications_inapp.py``.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# R4/R7 — GET sin registro previo devuelve defaults
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_without_existing_row_returns_none_defaults(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user
) -> None:
    _owner, token = user

    response = await client.get("/notification-preferences", headers=_auth(token))

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["frequency"] == "none"
    assert data["hour"] == 8
    assert data["weekday"] is None


# ---------------------------------------------------------------------------
# R7 — PUT con frecuencia inválida
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_invalid_frequency_returns_422_with_detail(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user
) -> None:
    _owner, token = user

    response = await client.put(
        "/notification-preferences",
        json={"frequency": "hourly", "hour": 8},
        headers=_auth(token),
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["detail"]
    assert body["code"] == "validation_error"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_invalid_hour_returns_422(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user
) -> None:
    """Triangulation: an out-of-range hour is a DIFFERENT invalid field than
    an invalid frequency — proves validation is real, not hardcoded to one field."""

    _owner, token = user

    response = await client.put(
        "/notification-preferences",
        json={"frequency": "daily", "hour": 25},
        headers=_auth(token),
    )

    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# R7 — PUT válido persiste y es legible por un GET posterior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_valid_persists_and_is_readable_by_subsequent_get(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user
) -> None:
    _owner, token = user

    put_response = await client.put(
        "/notification-preferences",
        json={"frequency": "weekly", "hour": 9, "weekday": 1},
        headers=_auth(token),
    )
    assert put_response.status_code == 200, put_response.text
    assert put_response.json()["data"]["frequency"] == "weekly"

    get_response = await client.get("/notification-preferences", headers=_auth(token))
    assert get_response.status_code == 200
    data = get_response.json()["data"]
    assert data["frequency"] == "weekly"
    assert data["hour"] == 9
    assert data["weekday"] == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_twice_updates_in_place_no_duplicate_row(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user
) -> None:
    """Triangulation: a SECOND PUT with different values overwrites the same
    row (single row per user) rather than accumulating history."""

    from sqlalchemy import func, select

    from app.modules.notifications.models import NotificationPreference

    owner, token = user

    await client.put(
        "/notification-preferences",
        json={"frequency": "daily", "hour": 7},
        headers=_auth(token),
    )
    await client.put(
        "/notification-preferences",
        json={"frequency": "weekly", "hour": 10, "weekday": 3},
        headers=_auth(token),
    )

    result = await session.execute(
        select(func.count(NotificationPreference.id)).where(
            NotificationPreference.organization_id == tenant.id,
            NotificationPreference.user_id == owner.id,
        )
    )
    assert result.scalar_one() == 1


# ---------------------------------------------------------------------------
# R8 — Aislamiento multi-tenant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_preference_never_crosses_organizations(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """org A's preference is invisible to (and unmodifiable by) org B's caller."""

    put_a = await client.put(
        "/notification-preferences",
        json={"frequency": "weekly", "hour": 11, "weekday": 2},
        headers=_auth(two_orgs.a.token),
    )
    assert put_a.status_code == 200, put_a.text

    get_b = await client.get("/notification-preferences", headers=_auth(two_orgs.b.token))
    assert get_b.status_code == 200
    data_b = get_b.json()["data"]
    assert data_b["frequency"] == "none"  # org B never sees org A's weekly setting

    get_a = await client.get("/notification-preferences", headers=_auth(two_orgs.a.token))
    assert get_a.json()["data"]["frequency"] == "weekly"  # org A's own row is untouched
