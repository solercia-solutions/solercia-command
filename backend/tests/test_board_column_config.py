"""Tests for the runtime column configuration API (change 03-boards-persistentes, Batch D).

Covers boards.md "Configuración runtime de columnas" (R4) and "Reglas de
eliminación de columnas con tareas" (R5): rename/reorder/add never touch
task rows; remove either requires zero tasks or a valid reassignment target,
and the last column of a board can never be removed.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: AsyncClient, token: str, methodology: str, name: str) -> str:
    response = await client.post(
        "/projects", json={"name": name, "methodology": methodology}, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _get_board(client: AsyncClient, token: str, project_id: str) -> dict:
    response = await client.get(f"/projects/{project_id}/board", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ---------------------------------------------------------------------------
# T26/T27 — rename a column
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_rename_column_preserves_status_key_and_task_status(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    project_id = await _create_project(client, token, "kanban", "Rename Project")
    board = await _get_board(client, token, project_id)
    board_id = board["id"]
    doing_column = next(c for c in board["columns"] if c["status_key"] == "Doing")

    task_response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Assigned to Doing", "board_column_id": doing_column["id"]},
        headers=_auth(token),
    )
    assert task_response.status_code == 201, task_response.text
    task_id = task_response.json()["data"]["id"]

    rename_response = await client.patch(
        f"/boards/{board_id}/columns/{doing_column['id']}",
        json={"name": "En progreso"},
        headers=_auth(token),
    )
    assert rename_response.status_code == 200, rename_response.text
    renamed = rename_response.json()["data"]
    assert renamed["name"] == "En progreso"
    assert renamed["status_key"] == "Doing"

    task_get = await client.get(f"/tasks/{task_id}", headers=_auth(token))
    assert task_get.json()["data"]["status"] == "Doing"
    assert task_get.json()["data"]["board_column_id"] == doing_column["id"]


# ---------------------------------------------------------------------------
# T28/T29 — reorder columns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reorder_columns_persists_and_is_reflected_on_get(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    project_id = await _create_project(client, token, "kanban", "Reorder Project")
    board = await _get_board(client, token, project_id)
    board_id = board["id"]
    by_key = {c["status_key"]: c["id"] for c in board["columns"]}
    # [Backlog, Doing, Done] -> [Done, Backlog, Doing]
    new_order = [by_key["Done"], by_key["Backlog"], by_key["Doing"]]

    response = await client.patch(
        f"/boards/{board_id}/columns/reorder",
        json={"ordered_ids": new_order},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    assert [c["id"] for c in response.json()["data"]] == new_order

    refetched = await _get_board(client, token, project_id)
    assert [c["id"] for c in refetched["columns"]] == new_order
    assert [c["status_key"] for c in refetched["columns"]] == ["Done", "Backlog", "Doing"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reorder_columns_rejects_mismatched_id_set(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    project_id = await _create_project(client, token, "kanban", "Reorder Mismatch")
    board = await _get_board(client, token, project_id)
    board_id = board["id"]

    response = await client.patch(
        f"/boards/{board_id}/columns/reorder",
        json={"ordered_ids": [str(uuid.uuid4())]},
        headers=_auth(token),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_column_order"


# ---------------------------------------------------------------------------
# T30/T31 — add a column
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_add_column_to_empty_custom_board_enables_task_creation(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    project_id = await _create_project(client, token, "custom", "Custom Add Column")
    board = await _get_board(client, token, project_id)
    board_id = board["id"]
    assert board["columns"] == []

    add_response = await client.post(
        f"/boards/{board_id}/columns",
        json={"name": "Backlog"},
        headers=_auth(token),
    )
    assert add_response.status_code == 201, add_response.text
    added = add_response.json()["data"]
    assert added["name"] == "Backlog"
    assert added["status_key"]  # slug derived, non-empty
    assert added["order"] == 0

    task_response = await client.post(
        f"/projects/{project_id}/tasks", json={"title": "Now possible"}, headers=_auth(token)
    )
    assert task_response.status_code == 201, task_response.text
    assert task_response.json()["data"]["status"] == added["status_key"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_add_column_derives_unique_status_key_per_board(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Two columns with the same display name get DIFFERENT status_key slugs."""

    _, token = user
    project_id = await _create_project(client, token, "custom", "Custom Slug Collision")
    board = await _get_board(client, token, project_id)
    board_id = board["id"]

    first = await client.post(
        f"/boards/{board_id}/columns", json={"name": "To Do"}, headers=_auth(token)
    )
    second = await client.post(
        f"/boards/{board_id}/columns", json={"name": "To Do"}, headers=_auth(token)
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["status_key"] != second.json()["data"]["status_key"]


# ---------------------------------------------------------------------------
# T32/T33 — remove a column
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_remove_empty_column_succeeds(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    project_id = await _create_project(client, token, "kanban", "Remove Empty Column")
    board = await _get_board(client, token, project_id)
    board_id = board["id"]
    done_column = next(c for c in board["columns"] if c["status_key"] == "Done")

    response = await client.delete(
        f"/boards/{board_id}/columns/{done_column['id']}", headers=_auth(token)
    )
    assert response.status_code == 204, response.text

    refetched = await _get_board(client, token, project_id)
    assert len(refetched["columns"]) == 2
    assert all(c["status_key"] != "Done" for c in refetched["columns"])


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_remove_column_with_tasks_and_no_target_is_rejected(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    project_id = await _create_project(client, token, "kanban", "Remove With Tasks No Target")
    board = await _get_board(client, token, project_id)
    board_id = board["id"]
    doing_column = next(c for c in board["columns"] if c["status_key"] == "Doing")

    await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "In Doing", "board_column_id": doing_column["id"]},
        headers=_auth(token),
    )

    response = await client.delete(
        f"/boards/{board_id}/columns/{doing_column['id']}", headers=_auth(token)
    )
    assert response.status_code == 409
    assert response.json()["code"] == "column_has_tasks"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_remove_column_with_tasks_and_valid_target_reassigns(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    project_id = await _create_project(client, token, "kanban", "Remove With Reassign")
    board = await _get_board(client, token, project_id)
    board_id = board["id"]
    doing_column = next(c for c in board["columns"] if c["status_key"] == "Doing")
    backlog_column = next(c for c in board["columns"] if c["status_key"] == "Backlog")

    task_response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "In Doing", "board_column_id": doing_column["id"]},
        headers=_auth(token),
    )
    task_id = task_response.json()["data"]["id"]

    response = await client.delete(
        f"/boards/{board_id}/columns/{doing_column['id']}",
        params={"target_column_id": backlog_column["id"]},
        headers=_auth(token),
    )
    assert response.status_code == 204, response.text

    task_get = await client.get(f"/tasks/{task_id}", headers=_auth(token))
    task_data = task_get.json()["data"]
    assert task_data["board_column_id"] == backlog_column["id"]
    assert task_data["status"] == "Backlog"
    assert task_data["updated_by"] is not None

    refetched = await _get_board(client, token, project_id)
    assert len(refetched["columns"]) == 2


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_remove_last_column_is_rejected(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    project_id = await _create_project(client, token, "custom", "Remove Last Column")
    board = await _get_board(client, token, project_id)
    board_id = board["id"]

    add_response = await client.post(
        f"/boards/{board_id}/columns", json={"name": "Only Column"}, headers=_auth(token)
    )
    only_column_id = add_response.json()["data"]["id"]

    response = await client.delete(
        f"/boards/{board_id}/columns/{only_column_id}", headers=_auth(token)
    )
    assert response.status_code == 422
    assert response.json()["code"] == "cannot_remove_last_column"
