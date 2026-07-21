"""Tests for ``GET /projects/{id}/sprints/suggested-name`` (change 29-sprint-borrador).

A read-only endpoint that SUGGESTS the next sprint's name (via
``next_sprint_name`` + the project's most recent sprint) WITHOUT persisting
anything. Declared before any ``{sprint_id}``-scoped route (tasks.md 4.6)
so a future ``GET /projects/{id}/sprints/{sprint_id}`` route could never
capture ``suggested-name`` as a ``sprint_id`` path param.
"""

import pytest
from httpx import AsyncClient

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_scrum_project(client: AsyncClient, token: str, name: str) -> dict:
    response = await client.post(
        "/projects",
        json={"name": name, "methodology": "scrum"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_suggested_name_matches_next_sprint_name_given_last_sprint(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A project with an existing "PANDORA 2026-1" sprint suggests
    "PANDORA 2026-2" — same algorithm as ``next_sprint_name``."""

    _, token = user
    project = await _create_scrum_project(client, token, "Suggested Name Project")
    project_id = project["id"]

    created = await client.post(
        f"/projects/{project_id}/sprints",
        json={"name": "PANDORA 2026-1"},
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text

    response = await client.get(
        f"/projects/{project_id}/sprints/suggested-name", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["name"] == "PANDORA 2026-2"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_suggested_name_without_previous_sprint_uses_code(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A brand-new scrum project (no sprints yet) suggests
    ``f"{code} Sprint 1"``."""

    _, token = user
    project = await _create_scrum_project(client, token, "Fresh Suggested Project")
    project_id = project["id"]
    project_code = project["code"]

    response = await client.get(
        f"/projects/{project_id}/sprints/suggested-name", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["name"] == f"{project_code} Sprint 1"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_suggested_name_does_not_persist_anything(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Calling the endpoint twice returns the same suggestion both times and
    never creates a sprint — the collection stays empty."""

    _, token = user
    project = await _create_scrum_project(client, token, "No Persist Project")
    project_id = project["id"]

    first = await client.get(
        f"/projects/{project_id}/sprints/suggested-name", headers=_auth(token)
    )
    second = await client.get(
        f"/projects/{project_id}/sprints/suggested-name", headers=_auth(token)
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["name"] == second.json()["data"]["name"]

    listing = await client.get(
        f"/projects/{project_id}/sprints", headers=_auth(token)
    )
    assert listing.json()["data"] == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_suggested_name_rejects_project_without_sprints_enabled(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A ``kanban`` project rejects the suggestion with 422
    ``sprints_not_enabled`` — same gate as sprint creation/listing."""

    _, token = user
    response = await client.post(
        "/projects",
        json={"name": "Kanban Suggested Name", "methodology": "kanban"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    project_id = response.json()["data"]["id"]

    suggested = await client.get(
        f"/projects/{project_id}/sprints/suggested-name", headers=_auth(token)
    )

    assert suggested.status_code == 422
    assert suggested.json()["code"] == "sprints_not_enabled"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_suggested_name_requires_auth(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """No bearer token -> 401."""

    _, token = user
    project = await _create_scrum_project(client, token, "Auth Required Project")
    project_id = project["id"]

    response = await client.get(f"/projects/{project_id}/sprints/suggested-name")

    assert response.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_suggested_name_of_other_org_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """Org A cannot see org B's suggested name (tenant isolation) -> 404."""

    project = await _create_scrum_project(
        client, two_orgs.b.token, "Org B Suggested Name Project"
    )

    response = await client.get(
        f"/projects/{project['id']}/sprints/suggested-name",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404
