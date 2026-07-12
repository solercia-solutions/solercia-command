"""Tests for the activity module (change 05, Batch B).

R6 Captura en mutación de usuario · R7 Captura en mutación de sistema (cierre
de sprint) · R8 Historial por tarea (paginado desc) · R9 Actividad por
usuario/día · R10 Solo lectura (specs/activity-history/spec.md).

Uses the shared in-process fixtures (``client``/``tenant``/``user``).
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: AsyncClient, token: str, methodology: str = "kanban") -> str:
    response = await client.post(
        "/projects",
        json={"name": "Activity Project", "methodology": methodology},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_task(client: AsyncClient, token: str, project_id: str) -> str:
    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Ship the release"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


# ---------------------------------------------------------------------------
# R6 — Captura automática en mutaciones de usuario
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_status_change_via_patch_creates_history_row(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Moving a task to a different status leaves a TaskHistory row with actor_id."""

    owner, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)

    board = await client.get(f"/projects/{project_id}/board", headers=_auth(token))
    columns = board.json()["data"]["columns"]
    target_status = columns[1]["status_key"] if len(columns) > 1 else columns[0]["status_key"]

    response = await client.patch(
        f"/tasks/{task_id}", json={"status": target_status}, headers=_auth(token)
    )
    assert response.status_code == 200, response.text

    history = await client.get(f"/tasks/{task_id}/history", headers=_auth(token))
    assert history.status_code == 200, history.text
    rows = history.json()["data"]
    status_rows = [r for r in rows if r["field"] == "status"]
    assert len(status_rows) == 1
    assert status_rows[0]["new_value"] == target_status
    assert status_rows[0]["actor_id"] == str(owner.id)
    assert status_rows[0]["actor_type"] == "user"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_multiple_fields_in_one_patch_creates_multiple_rows(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Reassigning + estimating in the same PATCH creates two history rows."""

    owner, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)

    response = await client.patch(
        f"/tasks/{task_id}",
        json={"assignee_id": str(owner.id), "estimation_hours": 4},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text

    history = await client.get(f"/tasks/{task_id}/history", headers=_auth(token))
    fields = {r["field"] for r in history.json()["data"]}
    assert fields == {"assignee_id", "estimation_hours"}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_no_op_patch_creates_no_history_row(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Sending the current value again produces zero history rows for that field."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)

    task = await client.get(f"/tasks/{task_id}", headers=_auth(token))
    current_priority = task.json()["data"]["priority"]

    response = await client.patch(
        f"/tasks/{task_id}", json={"priority": current_priority}, headers=_auth(token)
    )
    assert response.status_code == 200, response.text

    history = await client.get(f"/tasks/{task_id}/history", headers=_auth(token))
    assert history.json()["meta"]["total"] == 0


# ---------------------------------------------------------------------------
# R7 — Captura en mutaciones generadas por el sistema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_close_sprint_leaves_system_history_row(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Closing a sprint stamps history with actor_type=system, actor_id=null."""

    _, token = user
    project_id = await _create_project(client, token, methodology="scrum")

    sprint_response = await client.post(
        f"/projects/{project_id}/sprints",
        json={"name": "Sprint with leftovers"},
        headers=_auth(token),
    )
    assert sprint_response.status_code == 201, sprint_response.text
    sprint_id = sprint_response.json()["data"]["id"]

    task_response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Incomplete task", "sprint_id": sprint_id},
        headers=_auth(token),
    )
    assert task_response.status_code == 201, task_response.text
    task_id = task_response.json()["data"]["id"]

    close_response = await client.post(
        f"/sprints/{sprint_id}/close", headers=_auth(token)
    )
    assert close_response.status_code == 200, close_response.text
    assert close_response.json()["data"]["tasks_moved"] == 1

    history = await client.get(f"/tasks/{task_id}/history", headers=_auth(token))
    rows = history.json()["data"]
    sprint_rows = [r for r in rows if r["field"] == "sprint_id"]
    assert len(sprint_rows) == 1
    assert sprint_rows[0]["actor_type"] == "system"
    assert sprint_rows[0]["actor_id"] is None
    assert sprint_rows[0]["old_value"] == sprint_id
    assert sprint_rows[0]["new_value"] is None


# ---------------------------------------------------------------------------
# R8 — Historial por tarea (paginado desc)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_history_timeline_ordered_most_recent_first(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Three changes at different moments come back newest-first by default."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)

    for priority in ("high", "low", "critical"):
        r = await client.patch(
            f"/tasks/{task_id}", json={"priority": priority}, headers=_auth(token)
        )
        assert r.status_code == 200, r.text

    history = await client.get(f"/tasks/{task_id}/history", headers=_auth(token))
    assert history.status_code == 200, history.text
    body = history.json()
    assert body["meta"]["total"] == 3
    values = [row["new_value"] for row in body["data"]]
    assert values == ["critical", "low", "high"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_history_listing_is_paginated(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``GET /tasks/{id}/history`` returns ``meta {page, size, total}`` when paginated."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)

    for priority in ("high", "low", "critical"):
        await client.patch(
            f"/tasks/{task_id}", json={"priority": priority}, headers=_auth(token)
        )

    response = await client.get(
        f"/tasks/{task_id}/history?page=1&size=2", headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"] == {"page": 1, "size": 2, "total": 3}
    assert len(body["data"]) == 2


# ---------------------------------------------------------------------------
# R9 — Actividad por usuario y día
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_user_activity_filtered_by_specific_day(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Two changes on day D and one on another day: ``?date=D`` returns only the two."""

    from app.modules.activity.models import TaskHistory
    from app.modules.projects.models import Project
    from app.modules.tasks.models import Task

    owner, token = user

    project = Project(
        organization_id=tenant.id, name="Activity Day Project", methodology="kanban",
        code="ACTD",
    )
    session.add(project)
    await session.flush()
    task = Task(project_id=project.id, title="Task", status="Backlog")
    session.add(task)
    await session.flush()

    day_d = datetime(2026, 2, 10, 9, 0, tzinfo=UTC)
    other_day = datetime(2026, 2, 12, 9, 0, tzinfo=UTC)
    session.add_all(
        [
            TaskHistory(
                organization_id=tenant.id,
                task_id=task.id,
                actor_id=owner.id,
                actor_type="user",
                field="status",
                old_value="Backlog",
                new_value="Doing",
                created_at=day_d,
            ),
            TaskHistory(
                organization_id=tenant.id,
                task_id=task.id,
                actor_id=owner.id,
                actor_type="user",
                field="priority",
                old_value="medium",
                new_value="high",
                created_at=day_d,
            ),
            TaskHistory(
                organization_id=tenant.id,
                task_id=task.id,
                actor_id=owner.id,
                actor_type="user",
                field="priority",
                old_value="high",
                new_value="critical",
                created_at=other_day,
            ),
        ]
    )
    await session.flush()

    response = await client.get(
        f"/users/{owner.id}/activity?date=2026-02-10", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["total"] == 2
    assert all(row["field"] in ("status", "priority") for row in body["data"])


# ---------------------------------------------------------------------------
# R10 — Historial de solo lectura
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_no_edit_or_delete_route_for_task_history(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """PATCH/DELETE on a history row is a 404 of routing, not authorization."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)
    await client.patch(
        f"/tasks/{task_id}", json={"priority": "high"}, headers=_auth(token)
    )
    history = await client.get(f"/tasks/{task_id}/history", headers=_auth(token))
    history_id = history.json()["data"][0]["id"]

    patch_response = await client.patch(
        f"/tasks/{task_id}/history/{history_id}",
        json={"field": "status"},
        headers=_auth(token),
    )
    assert patch_response.status_code == 404

    delete_response = await client.delete(
        f"/tasks/{task_id}/history/{history_id}", headers=_auth(token)
    )
    assert delete_response.status_code == 404
