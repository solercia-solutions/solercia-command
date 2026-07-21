"""Tests for ``POST /sprints/{id}/start`` and the dates guard on ``PATCH``
(change 29-sprint-borrador).

``start_sprint`` transitions ``draft -> active`` only when both dates are
present (422 ``sprint_missing_dates`` in Spanish otherwise); already
``active`` -> 409 ``sprint_already_started``; already ``closed`` -> 422
``sprint_already_closed`` (Reconciliación #2 — distinguishable from the 409
of ``/close`` by status code + endpoint). The same dates guard applies to
``PATCH /sprints/{id}`` with ``status="active"`` directly (Reconciliación
#3), decided explicitly by the orchestrator beyond the literal wording of
spec.md.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_scrum_project(client: AsyncClient, token: str, name: str) -> str:
    response = await client.post(
        "/projects",
        json={"name": name, "methodology": "scrum"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


async def _create_draft_sprint(
    client: AsyncClient, token: str, project_id: str, name: str
) -> str:
    response = await client.post(
        f"/projects/{project_id}/sprints",
        json={"name": name},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["status"] == "draft"
    return body["id"]


# ---------------------------------------------------------------------------
# POST /sprints/{id}/start
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_start_sprint_without_dates_returns_422_spanish_and_stays_draft(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A ``draft`` sprint with no dates -> 422, Spanish message, stays
    ``draft`` after the call."""

    _, token = user
    project_id = await _create_scrum_project(client, token, "Start Without Dates")
    sprint_id = await _create_draft_sprint(client, token, project_id, "S1")

    response = await client.post(
        f"/sprints/{sprint_id}/start", headers=_auth(token)
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert (
        body["detail"]
        == "El sprint necesita fecha de inicio y fin antes de iniciarse."
    )
    assert body["code"] == "sprint_missing_dates"

    after = await client.get(
        f"/projects/{project_id}/sprints", headers=_auth(token)
    )
    still_draft = next(s for s in after.json()["data"] if s["id"] == sprint_id)
    assert still_draft["status"] == "draft"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_start_sprint_with_both_dates_transitions_to_active(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A ``draft`` sprint with both dates fixed via ``PATCH`` -> ``POST
    .../start`` -> 200, ``active``."""

    _, token = user
    project_id = await _create_scrum_project(client, token, "Start With Dates")
    sprint_id = await _create_draft_sprint(client, token, project_id, "S1")

    patch = await client.patch(
        f"/sprints/{sprint_id}",
        json={
            "start_date": "2026-08-01T00:00:00Z",
            "end_date": "2026-08-14T00:00:00Z",
        },
        headers=_auth(token),
    )
    assert patch.status_code == 200, patch.text

    response = await client.post(
        f"/sprints/{sprint_id}/start", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "active"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_start_sprint_already_active_returns_409(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A sprint created directly with both dates (already ``active``) ->
    ``POST .../start`` -> 409 ``sprint_already_started``."""

    _, token = user
    project_id = await _create_scrum_project(client, token, "Already Active Start")

    created = await client.post(
        f"/projects/{project_id}/sprints",
        json={
            "name": "Already Active",
            "start_date": "2026-08-01T00:00:00Z",
            "end_date": "2026-08-14T00:00:00Z",
        },
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text
    sprint_id = created.json()["data"]["id"]
    assert created.json()["data"]["status"] == "active"

    response = await client.post(
        f"/sprints/{sprint_id}/start", headers=_auth(token)
    )

    assert response.status_code == 409
    assert response.json()["code"] == "sprint_already_started"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_start_sprint_already_closed_returns_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A ``closed`` sprint -> ``POST .../start`` -> 422
    ``sprint_already_closed`` (NOT 409 — that code is reserved for the
    idempotent ``/close`` re-close case)."""

    _, token = user
    project_id = await _create_scrum_project(client, token, "Closed Start")

    created = await client.post(
        f"/projects/{project_id}/sprints",
        json={
            "name": "To Be Closed",
            "start_date": "2026-08-01T00:00:00Z",
            "end_date": "2026-08-14T00:00:00Z",
        },
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text
    sprint_id = created.json()["data"]["id"]

    closed = await client.post(f"/sprints/{sprint_id}/close", headers=_auth(token))
    assert closed.status_code == 200, closed.text

    response = await client.post(
        f"/sprints/{sprint_id}/start", headers=_auth(token)
    )

    assert response.status_code == 422
    assert response.json()["code"] == "sprint_already_closed"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_start_sprint_not_found_returns_404(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A random UUID -> 404."""

    _, token = user

    response = await client.post(
        "/sprints/00000000-0000-0000-0000-000000000000/start",
        headers=_auth(token),
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_start_sprint_of_other_org_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Org A cannot start org B's sprint (tenant isolation) -> 404."""

    project_id = await _create_scrum_project(
        client, two_orgs.b.token, "Org B Scrum Project"
    )
    sprint_id = await _create_draft_sprint(
        client, two_orgs.b.token, project_id, "Org B Sprint"
    )

    response = await client.post(
        f"/sprints/{sprint_id}/start", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /sprints/{id} status=active — dates guard also applies here
# (Reconciliación #3, orchestrator's explicit decision)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_status_active_on_draft_without_dates_returns_422_and_stays_draft(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``PATCH`` with ``{"status": "active"}`` on a dateless ``draft`` -> 422
    ``sprint_missing_dates``, sprint stays ``draft``."""

    _, token = user
    project_id = await _create_scrum_project(client, token, "Patch Active No Dates")
    sprint_id = await _create_draft_sprint(client, token, project_id, "S1")

    response = await client.patch(
        f"/sprints/{sprint_id}", json={"status": "active"}, headers=_auth(token)
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "sprint_missing_dates"

    after = await client.get(
        f"/projects/{project_id}/sprints", headers=_auth(token)
    )
    still_draft = next(s for s in after.json()["data"] if s["id"] == sprint_id)
    assert still_draft["status"] == "draft"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_status_active_with_dates_in_same_payload_succeeds(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``PATCH`` with ``status="active"`` AND both dates in the SAME payload
    succeeds — the guard evaluates against the resulting state after
    applying the rest of the payload, not the state before the request."""

    _, token = user
    project_id = await _create_scrum_project(client, token, "Patch Active With Dates")
    sprint_id = await _create_draft_sprint(client, token, project_id, "S1")

    response = await client.patch(
        f"/sprints/{sprint_id}",
        json={
            "status": "active",
            "start_date": "2026-08-01T00:00:00Z",
            "end_date": "2026-08-14T00:00:00Z",
        },
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "active"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_add_dates_without_status_does_not_change_status(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``PATCH`` with only dates (no ``status``) -> 200, sprint stays
    ``draft`` ("Añadir fechas" does not change the state)."""

    _, token = user
    project_id = await _create_scrum_project(client, token, "Add Dates Only")
    sprint_id = await _create_draft_sprint(client, token, project_id, "S1")

    response = await client.patch(
        f"/sprints/{sprint_id}",
        json={
            "start_date": "2026-08-01T00:00:00Z",
            "end_date": "2026-08-14T00:00:00Z",
        },
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "draft"
