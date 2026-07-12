"""Tests for the labels module (change 04, Batch A).

R1 nombre único por proyecto · R2 asignar/desasignar · R3 filtro ``label_id``
· R4 borrado sin afectar tareas. Uses the shared in-process fixtures
(``client``/``tenant``/``user``): each test creates its own project through
the real HTTP surface.
"""

import pytest
from httpx import AsyncClient

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: AsyncClient, token: str, name: str = "Label Project") -> str:
    response = await client.post(
        "/projects",
        json={"name": name, "methodology": "kanban"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_task(client: AsyncClient, token: str, project_id: str, title: str) -> str:
    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": title},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_label(
    client: AsyncClient, token: str, project_id: str, name: str, color: str = "#FF0000"
) -> dict:
    response = await client.post(
        f"/projects/{project_id}/labels",
        json={"name": name, "color": color},
        headers=_auth(token),
    )
    return response


# ---------------------------------------------------------------------------
# T01 — RED: duplicate active name in the same project -> 422 (R1)
# T02 — GREEN: CRUD (creation, listing)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_label_success(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Creating a label with a unique name in an empty project succeeds (201)."""

    _, token = user
    project_id = await _create_project(client, token)

    response = await _create_label(client, token, project_id, "Urgente", "#FF0000")

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["name"] == "Urgente"
    assert body["color"] == "#FF0000"
    assert body["project_id"] == project_id


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_label_duplicate_name_in_same_project_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A second active label with the same name in the same project is rejected."""

    _, token = user
    project_id = await _create_project(client, token)

    first = await _create_label(client, token, project_id, "Urgente")
    assert first.status_code == 201, first.text

    second = await _create_label(client, token, project_id, "Urgente")

    assert second.status_code == 422, second.text
    assert second.json()["code"] == "duplicate_label_name"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_label_same_name_in_different_projects_both_succeed(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """The same label name in two distinct projects is allowed."""

    _, token = user
    project_a = await _create_project(client, token, "Project A")
    project_b = await _create_project(client, token, "Project B")

    response_a = await _create_label(client, token, project_a, "Urgente")
    response_b = await _create_label(client, token, project_b, "Urgente")

    assert response_a.status_code == 201, response_a.text
    assert response_b.status_code == 201, response_b.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_labels_returns_active_labels(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """GET /projects/{id}/labels returns every active label of the project."""

    _, token = user
    project_id = await _create_project(client, token)
    await _create_label(client, token, project_id, "Urgente")
    await _create_label(client, token, project_id, "Bloqueante")

    response = await client.get(f"/projects/{project_id}/labels", headers=_auth(token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["total"] == 2
    assert {label["name"] for label in body["data"]} == {"Urgente", "Bloqueante"}


# ---------------------------------------------------------------------------
# T03 — RED+GREEN: assign/unassign (R2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_assign_label_to_task_of_same_project(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Assigning a label to a task of the same project succeeds and is visible."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id, "Some task")
    label_response = await _create_label(client, token, project_id, "Urgente")
    label_id = label_response.json()["data"]["id"]

    response = await client.post(
        f"/tasks/{task_id}/labels", json={"label_id": label_id}, headers=_auth(token)
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["id"] == label_id


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_assign_label_from_other_project_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Assigning a label whose project differs from the task's project is rejected."""

    _, token = user
    project_a = await _create_project(client, token, "Project A")
    project_b = await _create_project(client, token, "Project B")
    task_id = await _create_task(client, token, project_a, "Task in A")
    label_response = await _create_label(client, token, project_b, "Urgente")
    label_id = label_response.json()["data"]["id"]

    response = await client.post(
        f"/tasks/{task_id}/labels", json={"label_id": label_id}, headers=_auth(token)
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "label_project_mismatch"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_unassign_label_removes_it_from_task(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Unassigning a label removes it from the task's active label set."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id, "Some task")
    label_response = await _create_label(client, token, project_id, "Urgente")
    label_id = label_response.json()["data"]["id"]

    await client.post(
        f"/tasks/{task_id}/labels", json={"label_id": label_id}, headers=_auth(token)
    )

    unassign_response = await client.delete(
        f"/tasks/{task_id}/labels/{label_id}", headers=_auth(token)
    )
    assert unassign_response.status_code == 204, unassign_response.text

    reassign_check = await client.post(
        f"/tasks/{task_id}/labels", json={"label_id": label_id}, headers=_auth(token)
    )
    # Re-assigning after unassign works and reports exactly 1 active label
    # again — proves the previous unassign actually removed the link.
    assert reassign_check.json()["meta"]["total"] == 1


# ---------------------------------------------------------------------------
# T04 — RED+GREEN: label_id filter on GET /projects/{id}/tasks (R3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_filter_tasks_by_label_id_returns_only_tagged_tasks(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``?label_id=`` returns only the tasks tagged with that label."""

    _, token = user
    project_id = await _create_project(client, token)
    tagged_1 = await _create_task(client, token, project_id, "Tagged 1")
    tagged_2 = await _create_task(client, token, project_id, "Tagged 2")
    await _create_task(client, token, project_id, "Untagged 1")
    await _create_task(client, token, project_id, "Untagged 2")
    await _create_task(client, token, project_id, "Untagged 3")

    label_response = await _create_label(client, token, project_id, "Urgente")
    label_id = label_response.json()["data"]["id"]

    for task_id in (tagged_1, tagged_2):
        await client.post(
            f"/tasks/{task_id}/labels", json={"label_id": label_id}, headers=_auth(token)
        )

    response = await client.get(
        f"/projects/{project_id}/tasks",
        params={"label_id": label_id},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["total"] == 2
    assert {t["id"] for t in body["data"]} == {tagged_1, tagged_2}


# ---------------------------------------------------------------------------
# T05 — RED+GREEN: deleting a label unlinks it without affecting tasks (R4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_label_unlinks_from_tasks_without_deleting_them(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Soft-deleting a label detaches it from all 3 tasks, which stay active."""

    _, token = user
    project_id = await _create_project(client, token)
    task_ids = [
        await _create_task(client, token, project_id, f"Task {i}") for i in range(3)
    ]
    label_response = await _create_label(client, token, project_id, "Urgente")
    label_id = label_response.json()["data"]["id"]

    for task_id in task_ids:
        await client.post(
            f"/tasks/{task_id}/labels", json={"label_id": label_id}, headers=_auth(token)
        )

    delete_response = await client.delete(f"/labels/{label_id}", headers=_auth(token))
    assert delete_response.status_code == 204, delete_response.text

    # The label no longer appears in the project's label list.
    list_response = await client.get(
        f"/projects/{project_id}/labels", headers=_auth(token)
    )
    assert list_response.json()["meta"]["total"] == 0

    # The filter no longer matches any task (the label is gone).
    filter_response = await client.get(
        f"/projects/{project_id}/tasks",
        params={"label_id": label_id},
        headers=_auth(token),
    )
    assert filter_response.json()["meta"]["total"] == 0

    # Every task is still active and untouched.
    for task_id in task_ids:
        task_response = await client.get(f"/tasks/{task_id}", headers=_auth(token))
        assert task_response.status_code == 200, task_response.text
