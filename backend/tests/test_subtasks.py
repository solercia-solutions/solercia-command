"""Tests for subtask creation and subtask estimation guard (Feature #4 — subtask part)."""

import pytest

try:
    from tests.conftest import skip_no_db
except ImportError:
    skip_no_db = pytest.mark.skip(reason="conftest not found")


# ---------------------------------------------------------------------------
# Unit tests — no DB needed
# ---------------------------------------------------------------------------


class TestSubtaskPointsGuard:
    """TaskCreate payload is valid — the estimation_points guard is in the service.

    We can at least confirm that the schema itself does not reject points so that
    the service gets to run its subtask-specific check.
    """

    def test_payload_with_points_is_valid_schema(self) -> None:
        import uuid

        from app.modules.tasks.schemas import TaskCreate

        # Schema validation should pass; service validation raises for subtasks.
        payload = TaskCreate(
            title="A subtask",
            parent_task_id=uuid.uuid4(),
            estimation_points=5,
        )
        assert payload.estimation_points == 5
        assert payload.parent_task_id is not None

    def test_payload_without_parent_has_no_restriction(self) -> None:
        from app.modules.tasks.schemas import TaskCreate

        payload = TaskCreate(title="Normal task", estimation_points=8)
        assert payload.estimation_points == 8


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@skip_no_db
async def test_create_subtask_rejects_points() -> None:
    """Creating a subtask with estimation_points raises 422."""

    import os

    import httpx

    base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    token = os.getenv("TEST_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
        r = await client.get("/projects")
        projects = r.json()["data"]
        # Pick a project whose methodology supports points (scrum).
        scrum = next((p for p in projects if p["methodology"] == "scrum"), projects[0])
        project_id = scrum["id"]

        # Create parent task.
        r = await client.post(
            f"/projects/{project_id}/tasks",
            json={"title": "Parent task"},
        )
        assert r.status_code == 201
        parent_id = r.json()["data"]["id"]

        # Attempt subtask with points — must fail.
        r = await client.post(
            f"/projects/{project_id}/tasks",
            json={
                "title": "Subtask with points",
                "parent_task_id": parent_id,
                "estimation_points": 3,
            },
        )
        assert r.status_code == 422
        assert r.json()["code"] == "subtask_points_not_allowed"


@pytest.mark.asyncio
@skip_no_db
async def test_create_subtask_allows_hours() -> None:
    """Subtasks accept estimation_hours (no velocity double-counting risk)."""

    import os

    import httpx

    base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    token = os.getenv("TEST_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
        r = await client.get("/projects")
        projects = r.json()["data"]
        # Kanban or planner support hours.
        non_scrum = next(
            (p for p in projects if p["methodology"] != "scrum"),
            projects[0],
        )
        project_id = non_scrum["id"]

        r = await client.post(
            f"/projects/{project_id}/tasks", json={"title": "Parent"}
        )
        assert r.status_code == 201
        parent_id = r.json()["data"]["id"]

        r = await client.post(
            f"/projects/{project_id}/tasks",
            json={
                "title": "Subtask with hours",
                "parent_task_id": parent_id,
                "estimation_hours": 4.0,
            },
        )
        assert r.status_code == 201
        subtask = r.json()["data"]
        assert subtask["task_type"] == "subtask"
        assert subtask["estimation_hours"] == 4.0
        assert subtask["estimation_points"] is None
