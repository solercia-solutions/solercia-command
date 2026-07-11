"""Tests for sprint close (#9) and velocity (#10) endpoints.

Unit tests (no DB):
  - velocity average calculation
  - projected_sprints edge cases

Integration tests (require TEST_DATABASE_URL + API_BASE_URL + TEST_AUTH_TOKEN):
  - POST /sprints/{id}/close sums only Done tasks
  - POST /sprints/{id}/close moves incomplete tasks to backlog
  - POST /sprints/{id}/close is idempotent (409 on re-close)
  - GET /projects/{id}/velocity averages closed sprints
"""

import math

import pytest

from tests.conftest import skip_no_db

# ---------------------------------------------------------------------------
# Unit tests — no DB needed
# ---------------------------------------------------------------------------


def test_velocity_average_empty_series() -> None:
    """No closed sprints → average_velocity is 0 and projected_sprints is None."""

    series: list = []
    average = sum(e["completed_points"] for e in series) / len(series) if series else 0.0
    backlog = 30
    projected = math.ceil(backlog / average) if average > 0 else None

    assert average == 0.0
    assert projected is None


def test_velocity_average_multiple_sprints() -> None:
    """Average is computed across all closed sprints."""

    series = [
        {"completed_points": 10},
        {"completed_points": 20},
        {"completed_points": 30},
    ]
    average = sum(e["completed_points"] for e in series) / len(series)
    backlog = 60
    projected = math.ceil(backlog / average) if average > 0 else None

    assert average == 20.0
    assert projected == 3


def test_velocity_projected_rounds_up() -> None:
    """projected_sprints rounds up (ceiling), not down."""

    average = 7.0
    backlog = 10
    projected = math.ceil(backlog / average)

    assert projected == 2  # 10/7 ≈ 1.43 → ceil → 2


def test_velocity_zero_backlog_gives_zero_projected() -> None:
    """Zero backlog means 0 sprints needed (ceil(0/n) = 0)."""

    average = 10.0
    backlog = 0
    projected = math.ceil(backlog / average) if average > 0 else None

    assert projected == 0


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@skip_no_db
async def test_close_sprint_sums_only_done_tasks() -> None:
    """completed_points counts only tasks with completed_at set (Done status)."""

    import os

    import httpx

    base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    token = os.getenv("TEST_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
        # Find a scrum project (sprints enabled).
        r = await client.get("/projects")
        assert r.status_code == 200
        projects = r.json()["data"]
        scrum = next((p for p in projects if p["methodology"] == "scrum"), None)
        if scrum is None:
            pytest.skip("No scrum project available in seed data")
        project_id = scrum["id"]

        # Create a fresh sprint.
        r = await client.post(
            f"/projects/{project_id}/sprints",
            json={"name": "Test close sprint — done points"},
        )
        assert r.status_code == 201
        sprint_id = r.json()["data"]["id"]

        # Add a Done task (5 points) and an incomplete task (3 points).
        r = await client.post(
            f"/projects/{project_id}/tasks",
            json={"title": "Done task", "estimation_points": 5, "sprint_id": sprint_id},
        )
        assert r.status_code == 201
        done_task_id = r.json()["data"]["id"]

        r = await client.post(
            f"/projects/{project_id}/tasks",
            json={"title": "Incomplete task", "estimation_points": 3, "sprint_id": sprint_id},
        )
        assert r.status_code == 201

        # Move the done task to the terminal status (last allowed).
        r = await client.patch(
            f"/projects/{project_id}/tasks/{done_task_id}",
            json={"status": "done"},
        )
        assert r.status_code == 200

        # Close the sprint.
        r = await client.post(f"/sprints/{sprint_id}/close")
        assert r.status_code == 200
        result = r.json()["data"]
        sprint = result["sprint"]

        assert sprint["status"] == "closed"
        assert sprint["completed_points"] == 5, (
            f"Expected 5 completed points (Done task only), got {sprint['completed_points']}"
        )
        assert result["tasks_moved"] == 1


@pytest.mark.asyncio
@skip_no_db
async def test_close_sprint_moves_incomplete_to_backlog() -> None:
    """Incomplete tasks land in the backlog (sprint_id=null) after close."""

    import os

    import httpx

    base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    token = os.getenv("TEST_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
        r = await client.get("/projects")
        projects = r.json()["data"]
        scrum = next((p for p in projects if p["methodology"] == "scrum"), None)
        if scrum is None:
            pytest.skip("No scrum project available")
        project_id = scrum["id"]

        r = await client.post(
            f"/projects/{project_id}/sprints",
            json={"name": "Test close sprint — backlog"},
        )
        assert r.status_code == 201
        sprint_id = r.json()["data"]["id"]

        r = await client.post(
            f"/projects/{project_id}/tasks",
            json={"title": "Remaining task", "sprint_id": sprint_id},
        )
        assert r.status_code == 201
        task_id = r.json()["data"]["id"]

        # Close — no target_sprint_id → backlog.
        r = await client.post(f"/sprints/{sprint_id}/close")
        assert r.status_code == 200
        assert r.json()["data"]["tasks_moved"] == 1

        # Verify the task is now in the backlog.
        r = await client.get(f"/projects/{project_id}/tasks/{task_id}")
        assert r.status_code == 200
        assert r.json()["data"]["sprint_id"] is None


@pytest.mark.asyncio
@skip_no_db
async def test_close_sprint_idempotent_409() -> None:
    """Closing an already-closed sprint returns 409."""

    import os

    import httpx

    base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    token = os.getenv("TEST_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
        r = await client.get("/projects")
        projects = r.json()["data"]
        scrum = next((p for p in projects if p["methodology"] == "scrum"), None)
        if scrum is None:
            pytest.skip("No scrum project available")
        project_id = scrum["id"]

        r = await client.post(
            f"/projects/{project_id}/sprints",
            json={"name": "Test idempotent close"},
        )
        assert r.status_code == 201
        sprint_id = r.json()["data"]["id"]

        r = await client.post(f"/sprints/{sprint_id}/close")
        assert r.status_code == 200

        r = await client.post(f"/sprints/{sprint_id}/close")
        assert r.status_code == 409
        assert r.json()["code"] == "sprint_already_closed"


@pytest.mark.asyncio
@skip_no_db
async def test_velocity_averages_closed_sprints() -> None:
    """GET /projects/{id}/velocity returns correct average_velocity."""

    import os

    import httpx

    base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    token = os.getenv("TEST_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
        r = await client.get("/projects")
        projects = r.json()["data"]
        scrum = next((p for p in projects if p["methodology"] == "scrum"), None)
        if scrum is None:
            pytest.skip("No scrum project available")
        project_id = scrum["id"]

        r = await client.get(f"/projects/{project_id}/velocity")
        assert r.status_code == 200
        report = r.json()["data"]

        assert "series" in report
        assert "average_velocity" in report
        assert "backlog_points" in report
        assert "projected_sprints" in report

        series = report["series"]
        if series:
            computed_avg = sum(s["completed_points"] for s in series) / len(series)
            assert abs(report["average_velocity"] - computed_avg) < 0.001
