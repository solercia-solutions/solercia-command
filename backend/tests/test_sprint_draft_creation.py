"""Tests for creating sprints without a name / without dates (change 29-sprint-borrador).

``POST /projects/{id}/sprints`` now accepts an omitted/empty ``name`` (the
service auto-names it via ``next_sprint_name``) and derives the initial
``status`` from whether both dates are present: ``active`` when both
``start_date``/``end_date`` are given (backwards compatible), ``draft``
otherwise (missing both or only one). The ``sprints_enabled`` gate is
unchanged.
"""

import pytest
from httpx import AsyncClient

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_sprint_without_name_and_without_dates_is_draft_with_autoname(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """No ``name`` in the body -> 201, ``draft``, no dates, autonamed
    ``f"{project_code} Sprint 1"``."""

    _, token = user

    project_response = await client.post(
        "/projects",
        json={"name": "Autoname Draft Project", "methodology": "scrum"},
        headers=_auth(token),
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()["data"]
    project_id = project["id"]
    project_code = project["code"]

    response = await client.post(
        f"/projects/{project_id}/sprints", json={}, headers=_auth(token)
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["status"] == "draft"
    assert body["start_date"] is None
    assert body["end_date"] is None
    assert body["name"] == f"{project_code} Sprint 1"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_sprint_with_empty_string_name_also_uses_autoname(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A whitespace-only ``name`` behaves the same as an omitted one — no
    422 "name is required", autonamed instead."""

    _, token = user

    project_response = await client.post(
        "/projects",
        json={"name": "Blank Name Project", "methodology": "scrum"},
        headers=_auth(token),
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()["data"]
    project_id = project["id"]
    project_code = project["code"]

    response = await client.post(
        f"/projects/{project_id}/sprints",
        json={"name": "   "},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["status"] == "draft"
    assert body["name"] == f"{project_code} Sprint 1"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_sprint_autoname_uses_last_sprint_by_created_at(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A second sprint (no name) autonames off the most recently created
    sprint, incrementing its trailing run of digits."""

    _, token = user

    project_response = await client.post(
        "/projects",
        json={"name": "Consecutive Autoname Project", "methodology": "scrum"},
        headers=_auth(token),
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["data"]["id"]

    first = await client.post(
        f"/projects/{project_id}/sprints",
        json={"name": "PANDORA 2026-1"},
        headers=_auth(token),
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/projects/{project_id}/sprints", json={}, headers=_auth(token)
    )

    assert second.status_code == 201, second.text
    assert second.json()["data"]["name"] == "PANDORA 2026-2"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_sprint_with_both_dates_is_active_backwards_compatible(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``name`` + both dates -> 201, ``active`` (unchanged legacy behavior)."""

    _, token = user

    project_response = await client.post(
        "/projects",
        json={"name": "Both Dates Project", "methodology": "scrum"},
        headers=_auth(token),
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["data"]["id"]

    response = await client.post(
        f"/projects/{project_id}/sprints",
        json={
            "name": "Sprint With Dates",
            "start_date": "2026-08-01T00:00:00Z",
            "end_date": "2026-08-14T00:00:00Z",
        },
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["status"] == "active"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_sprint_with_only_one_date_is_still_draft(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``name`` + only ``start_date`` (no ``end_date``) -> 201, still
    ``draft`` — a single date is not enough."""

    _, token = user

    project_response = await client.post(
        "/projects",
        json={"name": "One Date Project", "methodology": "scrum"},
        headers=_auth(token),
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["data"]["id"]

    response = await client.post(
        f"/projects/{project_id}/sprints",
        json={"name": "Half Dated", "start_date": "2026-08-01T00:00:00Z"},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["status"] == "draft"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_sprint_still_rejects_project_without_sprints_enabled(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A ``kanban`` project (``sprints_enabled=False``) still rejects sprint
    creation with 422 even without a ``name`` in the body — the existing gate
    is unchanged."""

    _, token = user

    project_response = await client.post(
        "/projects",
        json={"name": "Kanban No Sprints", "methodology": "kanban"},
        headers=_auth(token),
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["data"]["id"]

    response = await client.post(
        f"/projects/{project_id}/sprints", json={}, headers=_auth(token)
    )

    assert response.status_code == 422
    assert response.json()["code"] == "sprints_not_enabled"
