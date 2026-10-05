"""Tests for the ``year`` filter and task counts on ``GET /projects`` and for
``GET /projects/years`` (ODD sdm-sync-y-paginas-pandora, S05).

A project "belongs" to a year when it has active tasks whose ``created_at``
falls in that calendar year in ``America/Bogota`` — the same criterion as the
task filter of S02. ``open_task_count`` counts tasks not completed
(``completed_at IS NULL``) and not ``cancelled``.
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


async def _create_project(client: AsyncClient, token: str, name: str) -> str:
    response = await client.post(
        "/projects", json={"name": name, "methodology": "kanban"}, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_task_at(
    client: AsyncClient,
    session: AsyncSession,
    token: str,
    project_id: str,
    created_at: datetime,
    **values: object,
) -> str:
    """Create a task through the API, then backdate it (and apply ``values``)."""

    response = await client.post(
        f"/projects/{project_id}/tasks", json={"title": "Tarea"}, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    task_id = response.json()["data"]["id"]
    await session.execute(
        update(Task)
        .where(Task.id == uuid.UUID(task_id))
        .values(created_at=created_at, **values)
    )
    await session.flush()
    return task_id


def _by_id(response_json: dict) -> dict[str, dict]:
    return {row["id"]: row for row in response_json["data"]}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_year_keeps_only_projects_with_tasks_created_that_year(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """``?year=2026`` drops a project whose tasks are all from 2025 and an empty one."""

    _, token = user
    with_2026 = await _create_project(client, token, "Con 2026")
    only_2025 = await _create_project(client, token, "Solo 2025")
    empty = await _create_project(client, token, "Sin tareas")
    await _create_task_at(client, session, token, with_2026, datetime(2026, 5, 1, 15, tzinfo=UTC))
    await _create_task_at(client, session, token, with_2026, datetime(2025, 5, 1, 15, tzinfo=UTC))
    await _create_task_at(client, session, token, only_2025, datetime(2025, 5, 1, 15, tzinfo=UTC))

    response = await client.get("/projects", params={"year": 2026}, headers=_auth(token))

    assert response.status_code == 200, response.text
    ids = set(_by_id(response.json()))
    assert with_2026 in ids
    assert only_2025 not in ids
    assert empty not in ids
    assert response.json()["meta"]["total"] == len(ids)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_year_uses_bogota_calendar_and_ignores_soft_deleted_tasks(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """2026-01-01T03:00Z is 2025 in Bogotá; a soft-deleted 2026 task does not count."""

    _, token = user
    project = await _create_project(client, token, "Frontera")
    await _create_task_at(client, session, token, project, datetime(2026, 1, 1, 3, tzinfo=UTC))
    await _create_task_at(
        client, session, token, project, datetime(2026, 6, 1, 15, tzinfo=UTC), is_active=False
    )

    r2025 = await client.get("/projects", params={"year": 2025}, headers=_auth(token))
    r2026 = await client.get("/projects", params={"year": 2026}, headers=_auth(token))

    assert project in _by_id(r2025.json())
    assert project not in _by_id(r2026.json())


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_and_open_counts_follow_the_year(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Counts are per year; open excludes completed (``completed_at``) and cancelled."""

    _, token = user
    project = await _create_project(client, token, "Conteos")
    in_2026 = datetime(2026, 4, 1, 15, tzinfo=UTC)
    await _create_task_at(client, session, token, project, in_2026)
    await _create_task_at(client, session, token, project, in_2026)
    await _create_task_at(client, session, token, project, in_2026, completed_at=in_2026)
    await _create_task_at(client, session, token, project, in_2026, status="cancelled")
    await _create_task_at(client, session, token, project, datetime(2025, 4, 1, 15, tzinfo=UTC))
    await _create_task_at(
        client, session, token, project, in_2026, is_active=False
    )

    r2026 = await client.get("/projects", params={"year": 2026}, headers=_auth(token))
    every_year = await client.get("/projects", headers=_auth(token))

    row_2026 = _by_id(r2026.json())[project]
    assert (row_2026["task_count"], row_2026["open_task_count"]) == (4, 2)
    row_all = _by_id(every_year.json())[project]
    assert (row_all["task_count"], row_all["open_task_count"]) == (5, 3)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_counts_exclude_subtasks_but_subtasks_still_mark_the_year(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Counts match the workspace header (top-level tasks only); a subtask of
    the year still makes the project belong to it (same as ``/tasks/years``)."""

    _, token = user
    project = await _create_project(client, token, "Subtareas")
    parent = await _create_task_at(
        client, session, token, project, datetime(2025, 2, 1, 15, tzinfo=UTC)
    )
    await _create_task_at(
        client,
        session,
        token,
        project,
        datetime(2025, 2, 2, 15, tzinfo=UTC),
        parent_task_id=uuid.UUID(parent),
    )
    await _create_task_at(
        client,
        session,
        token,
        project,
        datetime(2024, 2, 2, 15, tzinfo=UTC),
        parent_task_id=uuid.UUID(parent),
    )

    r2025 = await client.get("/projects", params={"year": 2025}, headers=_auth(token))
    r2024 = await client.get("/projects", params={"year": 2024}, headers=_auth(token))

    row_2025 = _by_id(r2025.json())[project]
    assert (row_2025["task_count"], row_2025["open_task_count"]) == (1, 1)
    row_2024 = _by_id(r2024.json())[project]
    assert (row_2024["task_count"], row_2024["open_task_count"]) == (0, 0)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_project_without_tasks_reports_zero_counts(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Without ``year`` a project with no tasks stays listed with zero counts."""

    _, token = user
    project = await _create_project(client, token, "Vacío")

    response = await client.get("/projects", headers=_auth(token))

    row = _by_id(response.json())[project]
    assert (row["task_count"], row["open_task_count"]) == (0, 0)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
@pytest.mark.parametrize("year", [1999, 2101, "dos-mil"])
async def test_project_year_out_of_range_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str], year: object
) -> None:
    """``year`` outside 2000–2100 (or not an integer) is rejected with 422."""

    _, token = user

    response = await client.get("/projects", params={"year": year}, headers=_auth(token))

    assert response.status_code == 422, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_project_years_are_distinct_descending_in_bogota(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """``/projects/years`` lists each year with tasks once, newest first, across projects."""

    _, token = user
    first = await _create_project(client, token, "Uno")
    second = await _create_project(client, token, "Dos")
    await _create_project(client, token, "Sin tareas")
    await _create_task_at(client, session, token, first, datetime(2024, 3, 1, 15, tzinfo=UTC))
    await _create_task_at(client, session, token, first, datetime(2026, 3, 1, 15, tzinfo=UTC))
    await _create_task_at(client, session, token, second, datetime(2026, 1, 1, 3, tzinfo=UTC))
    await _create_task_at(
        client, session, token, second, datetime(2023, 3, 1, 15, tzinfo=UTC), is_active=False
    )

    response = await client.get("/projects/years", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert response.json()["data"] == [2026, 2025, 2024]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_project_year_filter_and_years_are_isolated_by_organization(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Org A never sees org B's projects nor the years of org B's tasks."""

    await session.execute(
        update(Task)
        .where(Task.id == two_orgs.b.task.id)
        .values(created_at=datetime(2021, 6, 1, 15, tzinfo=UTC))
    )
    await session.execute(
        update(Task)
        .where(Task.id == two_orgs.a.task.id)
        .values(created_at=datetime(2022, 6, 1, 15, tzinfo=UTC))
    )
    await session.flush()
    token_a = two_orgs.a.token

    years = await client.get("/projects/years", headers=_auth(token_a))
    listed = await client.get("/projects", params={"year": 2021}, headers=_auth(token_a))

    assert years.status_code == 200, years.text
    assert years.json()["data"] == [2022]
    assert str(two_orgs.b.project.id) not in _by_id(listed.json())


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_project_years_requires_authentication(client: AsyncClient) -> None:
    """Without a bearer token ``/projects/years`` is rejected (401)."""

    response = await client.get("/projects/years")

    assert response.status_code == 401, response.text
