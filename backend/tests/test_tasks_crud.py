"""Tests for tasks CRUD, methodology validation, subtask progress and filters.

CRUD básico (create/get/update/delete/list) · R2 estado ajeno a la strategy
planner rechazado (camino ``PATCH /tasks/{id}`` directo, sin pasar por
``/tasks/{id}/column`` — no duplica ``test_board_move_to_column.py``) · R3
progreso agregado de subtareas · R4 filtros combinables ``sprint_id`` +
``status`` + ``assignee_id`` (openspec/specs/tasks/spec.md).

R1/R5/R6 ya cubiertos por ``test_task_key.py``/``test_board_column_tasks.py``/
``test_boards_backfill_migration.py`` — no se duplican aquí.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: AsyncClient, token: str, methodology: str = "planner") -> str:
    response = await client.post(
        "/projects",
        json={"name": f"{methodology.title()} CRUD Project", "methodology": methodology},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


# ---------------------------------------------------------------------------
# CRUD básico
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_crud_lifecycle(client: AsyncClient, tenant, user) -> None:
    """create -> get -> update -> delete -> list reflects the deletion."""

    _, token = user
    project_id = await _create_project(client, token)

    create_response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Lifecycle task"},
        headers=_auth(token),
    )
    assert create_response.status_code == 201, create_response.text
    task_id = create_response.json()["data"]["id"]

    get_response = await client.get(f"/tasks/{task_id}", headers=_auth(token))
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["data"]["title"] == "Lifecycle task"

    update_response = await client.patch(
        f"/tasks/{task_id}", json={"title": "Updated title"}, headers=_auth(token)
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["data"]["title"] == "Updated title"

    delete_response = await client.delete(f"/tasks/{task_id}", headers=_auth(token))
    assert delete_response.status_code == 204

    after_delete = await client.get(f"/tasks/{task_id}", headers=_auth(token))
    assert after_delete.status_code == 404

    listing = await client.get(
        f"/projects/{project_id}/tasks", headers=_auth(token)
    )
    listed_ids = {row["id"] for row in listing.json()["data"]}
    assert task_id not in listed_ids


# ---------------------------------------------------------------------------
# R2 — PATCH rechaza estado ajeno a la strategy (planner, camino directo)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_rejects_status_outside_planner_strategy(
    client: AsyncClient, tenant, user
) -> None:
    """A planner task's ``status`` cannot move to ``in_review`` — that value
    belongs to scrum's strategy, not planner's.
    """

    _, token = user
    project_id = await _create_project(client, token, "planner")
    task = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Planner task"},
        headers=_auth(token),
    )
    task_id = task.json()["data"]["id"]

    response = await client.patch(
        f"/tasks/{task_id}", json={"status": "in_review"}, headers=_auth(token)
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# R3 — Progreso agregado de subtareas (2/4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_subtask_progress_reports_two_of_four_completed(
    client: AsyncClient, tenant, user
) -> None:
    """A parent task with 4 subtasks, 2 completed, reports ``subtask_progress
    == 0.5`` on its detail read.
    """

    _, token = user
    project_id = await _create_project(client, token, "planner")
    parent = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Parent task"},
        headers=_auth(token),
    )
    parent_id = parent.json()["data"]["id"]

    subtask_ids = []
    for i in range(4):
        sub = await client.post(
            f"/projects/{project_id}/tasks",
            json={"title": f"Subtask {i}", "parent_task_id": parent_id},
            headers=_auth(token),
        )
        assert sub.status_code == 201, sub.text
        subtask_ids.append(sub.json()["data"]["id"])

    for sub_id in subtask_ids[:2]:
        done = await client.patch(
            f"/tasks/{sub_id}", json={"status": "Completada"}, headers=_auth(token)
        )
        assert done.status_code == 200, done.text

    detail = await client.get(f"/tasks/{parent_id}", headers=_auth(token))

    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["subtask_progress"] == 0.5


# ---------------------------------------------------------------------------
# R4 — Filtros combinables sprint_id + status + assignee_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_listing_filters_are_combinable(
    client: AsyncClient, tenant, user
) -> None:
    """``sprint_id``+``status``+``assignee_id`` narrow the listing together,
    not just individually.
    """

    owner, token = user
    project_id = await _create_project(client, token, "scrum")

    sprint_response = await client.post(
        f"/projects/{project_id}/sprints",
        json={"name": "Filter Sprint"},
        headers=_auth(token),
    )
    sprint_id = sprint_response.json()["data"]["id"]

    matching = await client.post(
        f"/projects/{project_id}/tasks",
        json={
            "title": "Matches all filters",
            "sprint_id": sprint_id,
            "assignee_id": str(owner.id),
        },
        headers=_auth(token),
    )
    matching_id = matching.json()["data"]["id"]

    # Same sprint, same assignee, DIFFERENT status: move it away from "To Do".
    other_status = await client.post(
        f"/projects/{project_id}/tasks",
        json={
            "title": "Same sprint, diff status",
            "sprint_id": sprint_id,
            "assignee_id": str(owner.id),
        },
        headers=_auth(token),
    )
    other_status_id = other_status.json()["data"]["id"]
    await client.patch(
        f"/tasks/{other_status_id}",
        json={"status": "In Progress"},
        headers=_auth(token),
    )

    # Different sprint entirely (backlog): should never match.
    await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "No sprint", "assignee_id": str(owner.id)},
        headers=_auth(token),
    )

    response = await client.get(
        f"/projects/{project_id}/tasks",
        params={"sprint_id": sprint_id, "status": "To Do", "assignee_id": str(owner.id)},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert ids == {matching_id}


# ---------------------------------------------------------------------------
# Aislamiento entre organizaciones (two_orgs)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_tasks_listing_never_crosses_organizations(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """``GET /projects/{id}/tasks`` for org A's own project never surfaces a
    task created directly under org B's project (blocked at the project
    lookup itself, before task filtering even runs).
    """

    response = await client.get(
        f"/projects/{two_orgs.b.project.id}/tasks", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_patch_delete_task_of_other_org_is_rejected(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """GET/PATCH/DELETE on a task belonging to org B, called by a member of
    org A, is rejected — never 200/204 with foreign data touched.
    """

    get_response = await client.get(
        f"/tasks/{two_orgs.b.task.id}", headers=_auth(two_orgs.a.token)
    )
    patch_response = await client.patch(
        f"/tasks/{two_orgs.b.task.id}",
        json={"title": "Hijacked"},
        headers=_auth(two_orgs.a.token),
    )
    delete_response = await client.delete(
        f"/tasks/{two_orgs.b.task.id}", headers=_auth(two_orgs.a.token)
    )

    assert get_response.status_code == 404
    assert patch_response.status_code == 404
    assert delete_response.status_code == 404
