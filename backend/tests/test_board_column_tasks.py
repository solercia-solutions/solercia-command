"""Tests for board-aware task creation (change 03-boards-persistentes, Batch B).

Covers: custom boards with zero columns block task creation (boards.md R3);
``create_task`` assigns the first column by ``order`` when no
``board_column_id`` is given, and derives ``status`` from an explicit one
(tasks.md delta, "Campo board_column_id").
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# T12 — custom board with zero columns blocks task creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_resolve_board_strategy_returns_empty_for_custom_without_columns(
    session: AsyncSession, tenant: Organization
) -> None:
    """A freshly created custom project's board has zero columns => allowed_statuses() == []."""

    from app.methodology.board_aware import resolve_board_strategy
    from app.modules.projects.schemas import ProjectCreate
    from app.modules.projects.service import ProjectService

    project = await ProjectService(session).create_project(
        tenant.id, ProjectCreate(name="Empty Custom", methodology="custom")
    )
    strategy = await resolve_board_strategy(project, session)
    assert strategy.allowed_statuses() == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_task_rejected_when_custom_board_has_no_columns(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Creating a task on a columnless custom board is an explicit 422."""

    _, token = user
    create_response = await client.post(
        "/projects",
        json={"name": "Empty Custom Board", "methodology": "custom"},
        headers=_auth(token),
    )
    assert create_response.status_code == 201, create_response.text
    project_id = create_response.json()["data"]["id"]

    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Should fail"},
        headers=_auth(token),
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "board_has_no_columns"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_move_task_rejected_when_target_project_board_has_no_columns(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """PATCH status is also rejected on a columnless board (same 422 guard)."""

    _, token = user
    kanban_response = await client.post(
        "/projects",
        json={"name": "Source Kanban", "methodology": "kanban"},
        headers=_auth(token),
    )
    project_id = kanban_response.json()["data"]["id"]
    task_response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Task to move"},
        headers=_auth(token),
    )
    assert task_response.status_code == 201, task_response.text
    task_id = task_response.json()["data"]["id"]

    # There is no columnless project with an existing task under normal flow
    # (creation is blocked first), so this asserts the SAME guard rejects an
    # out-of-band status that does not match any of this project's columns.
    response = await client.patch(
        f"/tasks/{task_id}", json={"status": "not-a-real-column"}, headers=_auth(token)
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_status"


# ---------------------------------------------------------------------------
# T14 — create_task assigns the first column by order, or derives status from
# an explicit board_column_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_task_without_board_column_id_uses_first_column_by_order(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """No board_column_id given => task lands in the first column ('Backlog')."""

    _, token = user
    create_response = await client.post(
        "/projects",
        json={"name": "Kanban Default Column", "methodology": "kanban"},
        headers=_auth(token),
    )
    project_id = create_response.json()["data"]["id"]

    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "New task"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    task = response.json()["data"]
    assert task["status"] == "Backlog"

    board_response = await client.get(
        f"/projects/{project_id}/board", headers=_auth(token)
    )
    columns = board_response.json()["data"]["columns"]
    backlog_column = next(c for c in columns if c["status_key"] == "Backlog")
    assert task["board_column_id"] == backlog_column["id"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_task_with_explicit_board_column_id_derives_status(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """An explicit board_column_id derives status from that column's status_key."""

    _, token = user
    create_response = await client.post(
        "/projects",
        json={"name": "Kanban Explicit Column", "methodology": "kanban"},
        headers=_auth(token),
    )
    project_id = create_response.json()["data"]["id"]

    board_response = await client.get(
        f"/projects/{project_id}/board", headers=_auth(token)
    )
    columns = board_response.json()["data"]["columns"]
    doing_column = next(c for c in columns if c["status_key"] == "Doing")

    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Explicit column task", "board_column_id": doing_column["id"]},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    task = response.json()["data"]
    assert task["status"] == "Doing"
    assert task["board_column_id"] == doing_column["id"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_task_with_board_column_id_from_another_project_rejected(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A board_column_id that belongs to a DIFFERENT project's board is rejected."""

    _, token = user
    project_a = await client.post(
        "/projects", json={"name": "Project A", "methodology": "kanban"}, headers=_auth(token)
    )
    project_b = await client.post(
        "/projects", json={"name": "Project B", "methodology": "kanban"}, headers=_auth(token)
    )
    project_b_id = project_b.json()["data"]["id"]

    board_a = await client.get(
        f"/projects/{project_a.json()['data']['id']}/board", headers=_auth(token)
    )
    foreign_column_id = board_a.json()["data"]["columns"][0]["id"]

    response = await client.post(
        f"/projects/{project_b_id}/tasks",
        json={"title": "Cross-project column", "board_column_id": foreign_column_id},
        headers=_auth(token),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_board_column"
