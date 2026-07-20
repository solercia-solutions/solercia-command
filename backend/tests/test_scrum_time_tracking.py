"""Scrum dual estimation: story points + time-tracking original estimate.

Feedback item 8 — a Jira-style scrum board estimates with story points AND
keeps a parallel "original estimate" in time (``estimation_hours``, parsed by
the frontend from 4w/2d/3h into hours). The scrum strategy therefore exposes
``estimation_mode == "both"`` so ``TaskService._validate_estimation`` accepts
both fields at once, while velocity keeps summing ``estimation_points`` only.

Regression guards: kanban stays hours-only, planner stays estimation-free,
and closed-sprint velocity ignores hours entirely.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(
    client: AsyncClient, token: str, methodology: str
) -> str:
    response = await client.post(
        "/projects",
        json={"name": f"{methodology.title()} Estimation", "methodology": methodology},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


# ---------------------------------------------------------------------------
# Scrum accepts points AND hours together (Jira-style)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_scrum_task_accepts_points_and_hours_together(
    client: AsyncClient, tenant, user
) -> None:
    """A scrum task carries story points and a time original estimate at the
    same time: 201, both values persisted and returned by TaskRead.
    """

    _, token = user
    project_id = await _create_project(client, token, "scrum")

    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={
            "title": "Story with dual estimation",
            "estimation_points": 5,
            "estimation_hours": 40,
        },
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["estimation_points"] == 5
    assert body["estimation_hours"] == 40

    # Both values survive a round-trip through GET /tasks/{id}.
    fetched = await client.get(f"/tasks/{body['id']}", headers=_auth(token))
    assert fetched.status_code == 200, fetched.text
    fetched_body = fetched.json()["data"]
    assert fetched_body["estimation_points"] == 5
    assert fetched_body["estimation_hours"] == 40


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_scrum_task_with_points_only_still_works(
    client: AsyncClient, tenant, user
) -> None:
    """Estimating a scrum task with story points only keeps working (201)."""

    _, token = user
    project_id = await _create_project(client, token, "scrum")

    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Points-only story", "estimation_points": 8},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["estimation_points"] == 8
    assert body["estimation_hours"] is None


# ---------------------------------------------------------------------------
# Regression — kanban stays hours-only, planner stays estimation-free
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_kanban_task_with_hours_only_still_works(
    client: AsyncClient, tenant, user
) -> None:
    """Kanban (mode ``hours``) keeps accepting hours and rejecting points."""

    _, token = user
    project_id = await _create_project(client, token, "kanban")

    with_hours = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Hours-only card", "estimation_hours": 6},
        headers=_auth(token),
    )
    assert with_hours.status_code == 201, with_hours.text
    assert with_hours.json()["data"]["estimation_hours"] == 6

    with_points = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Points on kanban", "estimation_points": 3},
        headers=_auth(token),
    )
    assert with_points.status_code == 422
    assert with_points.json()["code"] == "invalid_estimation"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_planner_task_rejects_any_estimation(
    client: AsyncClient, tenant, user
) -> None:
    """Planner (mode ``none``) keeps rejecting points and hours alike."""

    _, token = user
    project_id = await _create_project(client, token, "planner")

    with_points = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Points on planner", "estimation_points": 2},
        headers=_auth(token),
    )
    assert with_points.status_code == 422
    assert with_points.json()["code"] == "invalid_estimation"

    with_hours = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Hours on planner", "estimation_hours": 4},
        headers=_auth(token),
    )
    assert with_hours.status_code == 422
    assert with_hours.json()["code"] == "invalid_estimation"


# ---------------------------------------------------------------------------
# Velocity keeps summing story points only — hours never leak into it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_velocity_sums_points_even_when_tasks_carry_hours(
    client: AsyncClient, tenant, user
) -> None:
    """A closed scrum sprint whose done task carries points AND hours reports
    ``completed_points`` from ``estimation_points`` only (hours are ignored).
    """

    _, token = user
    project_id = await _create_project(client, token, "scrum")

    sprint = await client.post(
        f"/projects/{project_id}/sprints",
        json={"name": "Sprint 1"},
        headers=_auth(token),
    )
    assert sprint.status_code == 201, sprint.text
    sprint_id = sprint.json()["data"]["id"]

    task = await client.post(
        f"/projects/{project_id}/tasks",
        json={
            "title": "Dual-estimated done task",
            "sprint_id": sprint_id,
            "estimation_points": 5,
            "estimation_hours": 80,
        },
        headers=_auth(token),
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["data"]["id"]
    moved = await client.patch(
        f"/tasks/{task_id}", json={"status": "Done"}, headers=_auth(token)
    )
    assert moved.status_code == 200, moved.text

    close = await client.post(
        f"/sprints/{sprint_id}/close", headers=_auth(token)
    )
    assert close.status_code == 200, close.text
    assert close.json()["data"]["sprint"]["completed_points"] == 5

    response = await client.get(
        f"/projects/{project_id}/velocity", headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["series"][-1]["completed_points"] == 5
    assert body["average_velocity"] == 5.0
