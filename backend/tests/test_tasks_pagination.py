"""Pagination tests for ``GET /projects/{project_id}/tasks`` (R1, R2, R3, G3).

Uses the shared in-process fixtures (``client``/``tenant``/``user``): each
test creates its own project and tasks through the real HTTP surface, then
exercises the four pagination scenarios from ``specs/api-pagination.md``.
"""

import pytest
from httpx import AsyncClient

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/projects",
        json={"name": "Pagination Project", "methodology": "kanban"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_tasks(
    client: AsyncClient, token: str, project_id: str, titles: list[str]
) -> None:
    for title in titles:
        response = await client.post(
            f"/projects/{project_id}/tasks",
            json={"title": title},
            headers=_auth(token),
        )
        assert response.status_code == 201, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_tasks_without_params_is_byte_compatible(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """No pagination params → full collection, ``meta`` is exactly ``{total}``."""

    _, token = user
    project_id = await _create_project(client, token)
    await _create_tasks(client, token, project_id, ["Task 00", "Task 01", "Task 02"])

    response = await client.get(
        f"/projects/{project_id}/tasks", headers=_auth(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 3
    assert body["meta"] == {"total": 3}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_tasks_page_and_size_returns_correct_slice(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``?page=2&size=2&sort=title`` returns the third/fourth alphabetical tasks."""

    _, token = user
    project_id = await _create_project(client, token)
    await _create_tasks(
        client,
        token,
        project_id,
        ["Task 00", "Task 01", "Task 02", "Task 03", "Task 04"],
    )

    response = await client.get(
        f"/projects/{project_id}/tasks",
        params={"page": 2, "size": 2, "sort": "title", "order": "asc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 2, "size": 2, "total": 5}
    assert [t["title"] for t in body["data"]] == ["Task 02", "Task 03"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_tasks_sort_assignee_name_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``assignee_name`` is computed post-query — excluded from the whitelist (G3)."""

    _, token = user
    project_id = await _create_project(client, token)

    response = await client.get(
        f"/projects/{project_id}/tasks",
        params={"sort": "assignee_name"},
        headers=_auth(token),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_sort_field"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_tasks_sort_title_desc_orders_results(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``?sort=title&order=desc`` returns 200 ordered descending.

    Uses ``title`` (not ``created_at``, per the tasks.md scenario) because
    Postgres ``now()`` is transaction-scoped: every write inside the shared
    SAVEPOINT session gets the SAME ``created_at``, so it can't discriminate
    order. ``title`` exercises the identical code path (whitelist lookup +
    ``order_by``) with a deterministic value.
    """

    _, token = user
    project_id = await _create_project(client, token)
    await _create_tasks(client, token, project_id, ["Task 00", "Task 01", "Task 02"])

    response = await client.get(
        f"/projects/{project_id}/tasks",
        params={"sort": "title", "order": "desc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert [t["title"] for t in response.json()["data"]] == [
        "Task 02",
        "Task 01",
        "Task 00",
    ]
