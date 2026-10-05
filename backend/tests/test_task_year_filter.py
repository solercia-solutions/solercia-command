"""Tests for the ``year`` filter on ``GET /projects/{id}/tasks`` and for
``GET /projects/{id}/tasks/years`` (ODD sdm-sync-y-paginas-pandora, S02).

The year is the calendar year of ``created_at`` in ``America/Bogota``: the
filter is the half-open range ``[1-ene-year, 1-ene-(year+1))`` in that zone.
"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.tasks.models import Task
from app.modules.users.models import User
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/projects",
        json={"name": "Year Project", "methodology": "kanban"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_task_at(
    client: AsyncClient,
    session: AsyncSession,
    token: str,
    project_id: str,
    title: str,
    created_at: datetime,
) -> str:
    """Create a task through the API, then backdate its ``created_at``."""

    response = await client.post(
        f"/projects/{project_id}/tasks", json={"title": title}, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    task_id = response.json()["data"]["id"]
    await session.execute(
        update(Task).where(Task.id == uuid.UUID(task_id)).values(created_at=created_at)
    )
    await session.flush()
    return task_id


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_year_filter_keeps_only_tasks_created_that_year(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """``?year=2025`` keeps tasks created in 2025 and drops 2024/2026 ones."""

    _, token = user
    project_id = await _create_project(client, token)
    in_2025 = await _create_task_at(
        client, session, token, project_id, "De 2025", datetime(2025, 6, 1, 15, tzinfo=UTC)
    )
    in_2024 = await _create_task_at(
        client, session, token, project_id, "De 2024", datetime(2024, 6, 1, 15, tzinfo=UTC)
    )
    in_2026 = await _create_task_at(
        client, session, token, project_id, "De 2026", datetime(2026, 6, 1, 15, tzinfo=UTC)
    )

    response = await client.get(
        f"/projects/{project_id}/tasks",
        params={"year": 2025, "include_subtasks": "true"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    ids = [row["id"] for row in response.json()["data"]]
    assert ids == [in_2025]
    assert in_2024 not in ids
    assert in_2026 not in ids
    assert response.json()["meta"]["total"] == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_year_filter_uses_bogota_calendar_boundaries(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """2026-01-01T03:00Z is still 2025-12-31 in Bogotá (UTC-5): it belongs to 2025."""

    _, token = user
    project_id = await _create_project(client, token)
    late_2025_bogota = await _create_task_at(
        client, session, token, project_id, "Nochevieja", datetime(2026, 1, 1, 3, tzinfo=UTC)
    )
    first_2026_bogota = await _create_task_at(
        client, session, token, project_id, "Año nuevo", datetime(2026, 1, 1, 5, tzinfo=UTC)
    )

    r2025 = await client.get(
        f"/projects/{project_id}/tasks", params={"year": 2025}, headers=_auth(token)
    )
    r2026 = await client.get(
        f"/projects/{project_id}/tasks", params={"year": 2026}, headers=_auth(token)
    )

    assert r2025.status_code == 200, r2025.text
    assert [row["id"] for row in r2025.json()["data"]] == [late_2025_bogota]
    assert [row["id"] for row in r2026.json()["data"]] == [first_2026_bogota]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
@pytest.mark.parametrize("year", [1999, 2101, "dos-mil"])
async def test_year_out_of_range_or_not_numeric_is_422(
    client: AsyncClient,
    tenant: Organization,
    user: tuple[User, str],
    year: object,
) -> None:
    """``year`` outside 2000–2100 (or not an integer) is rejected with 422."""

    _, token = user
    project_id = await _create_project(client, token)

    response = await client.get(
        f"/projects/{project_id}/tasks", params={"year": year}, headers=_auth(token)
    )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_available_years_are_distinct_and_descending(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """``/tasks/years`` returns each year with data once, newest first (Bogotá zone)."""

    _, token = user
    project_id = await _create_project(client, token)
    for title, created in [
        ("A", datetime(2024, 3, 1, 15, tzinfo=UTC)),
        ("B", datetime(2026, 3, 1, 15, tzinfo=UTC)),
        ("C", datetime(2026, 8, 1, 15, tzinfo=UTC)),
        ("D", datetime(2026, 1, 1, 3, tzinfo=UTC)),  # 2025-12-31 en Bogotá
    ]:
        await _create_task_at(client, session, token, project_id, title, created)

    response = await client.get(f"/projects/{project_id}/tasks/years", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert response.json()["data"] == [2026, 2025, 2024]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_available_years_is_empty_for_project_without_tasks(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A project with no tasks answers an empty list, not an error."""

    _, token = user
    project_id = await _create_project(client, token)

    response = await client.get(f"/projects/{project_id}/tasks/years", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_available_years_and_year_filter_are_isolated_by_organization(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A member of org A cannot read years nor year-filtered tasks of org B's project."""

    project_b = two_orgs.b.project.id
    token_a = two_orgs.a.token

    years = await client.get(f"/projects/{project_b}/tasks/years", headers=_auth(token_a))
    tasks = await client.get(
        f"/projects/{project_b}/tasks", params={"year": 2026}, headers=_auth(token_a)
    )

    assert years.status_code == 404, years.text
    assert tasks.status_code == 404, tasks.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_available_years_requires_authentication(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """Without a bearer token the endpoint is rejected (401)."""

    response = await client.get(f"/projects/{two_orgs.a.project.id}/tasks/years")

    assert response.status_code == 401, response.text
