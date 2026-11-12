"""Tests for subtask creation and subtask estimation guard (Feature #4 — subtask part)."""

import pytest
from httpx import AsyncClient

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: AsyncClient, token: str, methodology: str) -> str:
    response = await client.post(
        "/projects",
        json={"name": f"Subtasks {methodology.capitalize()} Project", "methodology": methodology},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


async def _create_parent_task(client: AsyncClient, token: str, project_id: str) -> str:
    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Parent task"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


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
# Integration tests — shared in-process fixtures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_subtask_rejects_points(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Creating a subtask with estimation_points is rejected with 422."""

    _, token = user
    # A scrum project supports points, so the rejection comes from the
    # subtask-specific guard, not the methodology.
    project_id = await _create_project(client, token, "scrum")
    parent_id = await _create_parent_task(client, token, project_id)

    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={
            "title": "Subtask with points",
            "parent_task_id": parent_id,
            "estimation_points": 3,
        },
        headers=_auth(token),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "subtask_points_not_allowed"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_subtask_allows_hours(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Subtasks accept estimation_hours (no velocity double-counting risk)."""

    _, token = user
    project_id = await _create_project(client, token, "kanban")
    parent_id = await _create_parent_task(client, token, project_id)

    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={
            "title": "Subtask with hours",
            "parent_task_id": parent_id,
            "estimation_hours": 4.0,
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    subtask = response.json()["data"]
    assert subtask["task_type"] == "subtask"
    assert subtask["estimation_hours"] == 4.0
    assert subtask["estimation_points"] is None
