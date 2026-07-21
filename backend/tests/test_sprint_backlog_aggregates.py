"""Tests for backlog/sprint aggregates on ``GET /projects/{id}/sprints``
(change 30-backlog-sprints-agrupados).

The listing gains, per sprint, ``story_count`` (active tasks assigned to it)
and ``estimation_hours_sum`` (sum of their ``estimation_hours``), plus a
``meta.backlog`` aggregate for tasks with no sprint. Both are computed by a
SINGLE grouped query (``SprintRepository.aggregate_tasks_by_sprint``) so the
endpoint stays O(1) queries regardless of how many sprints a project has.
``SprintRead`` (used by ``burndown``/``close``/``PATCH``) is untouched —
the new fields live only in the list-item schema and ``meta``.
"""

import pytest
from httpx import AsyncClient

from app.modules.organizations.models import Organization
from app.modules.sprints.repository import SprintRepository
from app.modules.users.models import User
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_scrum_project(client: AsyncClient, token: str, name: str) -> dict:
    response = await client.post(
        "/projects",
        json={"name": name, "methodology": "scrum"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_sprint(client: AsyncClient, token: str, project_id: str, name: str) -> dict:
    response = await client.post(
        f"/projects/{project_id}/sprints",
        json={"name": name},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_task(
    client: AsyncClient,
    token: str,
    project_id: str,
    title: str,
    *,
    sprint_id: str | None = None,
    estimation_hours: float | None = None,
) -> dict:
    payload: dict = {"title": title}
    if sprint_id is not None:
        payload["sprint_id"] = sprint_id
    if estimation_hours is not None:
        payload["estimation_hours"] = estimation_hours
    response = await client.post(
        f"/projects/{project_id}/tasks", json=payload, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _item_for(sprints_data: list[dict], sprint_id: str) -> dict:
    for item in sprints_data:
        if item["id"] == sprint_id:
            return item
    raise AssertionError(f"sprint {sprint_id} not found in response data")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_sprints_reports_story_count_and_hours_sum_never_null(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Sprint A has 2 active tasks (2h + 3h) plus a deleted one; sprint B is
    freshly created without tasks. Neither field is ever null."""

    _, token = user
    project = await _create_scrum_project(client, token, "Aggregates Project A")
    project_id = project["id"]

    sprint_a = await _create_sprint(client, token, project_id, "Sprint A")
    sprint_b = await _create_sprint(client, token, project_id, "Sprint B")

    await _create_task(
        client, token, project_id, "Task 2h", sprint_id=sprint_a["id"], estimation_hours=2
    )
    await _create_task(
        client, token, project_id, "Task 3h", sprint_id=sprint_a["id"], estimation_hours=3
    )
    deleted_task = await _create_task(
        client, token, project_id, "Task deleted", sprint_id=sprint_a["id"], estimation_hours=99
    )
    delete_response = await client.delete(
        f"/tasks/{deleted_task['id']}", headers=_auth(token)
    )
    assert delete_response.status_code == 204

    response = await client.get(f"/projects/{project_id}/sprints", headers=_auth(token))
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    item_a = _item_for(data, sprint_a["id"])
    assert item_a["story_count"] == 2
    assert item_a["estimation_hours_sum"] == 5

    item_b = _item_for(data, sprint_b["id"])
    assert item_b["story_count"] == 0
    assert item_b["estimation_hours_sum"] == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_sprints_meta_includes_backlog_aggregate_with_and_without_tasks(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``meta.backlog`` reports the aggregate of tasks with no sprint (never null)."""

    _, token = user

    project_with_backlog = await _create_scrum_project(
        client, token, "Backlog Aggregate Project"
    )
    await _create_task(
        client, token, project_with_backlog["id"], "Loose task 4h", estimation_hours=4
    )
    await _create_task(
        client, token, project_with_backlog["id"], "Loose task 1h", estimation_hours=1
    )

    response_with = await client.get(
        f"/projects/{project_with_backlog['id']}/sprints", headers=_auth(token)
    )
    assert response_with.status_code == 200, response_with.text
    assert response_with.json()["meta"]["backlog"] == {
        "story_count": 2,
        "estimation_hours_sum": 5,
    }

    project_without_backlog = await _create_scrum_project(
        client, token, "Empty Backlog Aggregate Project"
    )
    response_without = await client.get(
        f"/projects/{project_without_backlog['id']}/sprints", headers=_auth(token)
    )
    assert response_without.status_code == 200, response_without.text
    assert response_without.json()["meta"]["backlog"] == {
        "story_count": 0,
        "estimation_hours_sum": 0,
    }


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_sprints_aggregates_respect_tenant_scoping_auth_and_permissions(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A member sees its own aggregates; no token is 401; another org's
    project is 404 — same permission model as the rest of the module."""

    project_a = await _create_scrum_project(
        client, two_orgs.a.token, "Scoping Aggregates Project"
    )
    sprint = await _create_sprint(
        client, two_orgs.a.token, project_a["id"], "Scoped Sprint"
    )
    await _create_task(
        client, two_orgs.a.token, project_a["id"], "Scoped task", sprint_id=sprint["id"]
    )

    own_response = await client.get(
        f"/projects/{project_a['id']}/sprints", headers=_auth(two_orgs.a.token)
    )
    assert own_response.status_code == 200, own_response.text
    own_item = _item_for(own_response.json()["data"], sprint["id"])
    assert own_item["story_count"] == 1

    no_token_response = await client.get(f"/projects/{project_a['id']}/sprints")
    assert no_token_response.status_code == 401

    other_org_response = await client.get(
        f"/projects/{two_orgs.b.project.id}/sprints", headers=_auth(two_orgs.a.token)
    )
    assert other_org_response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_aggregate_tasks_by_sprint_called_exactly_once_regardless_of_sprint_count(
    client: AsyncClient,
    tenant: Organization,
    user: tuple[User, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One grouped query covers every sprint AND the backlog — no N+1."""

    _, token = user
    project = await _create_scrum_project(client, token, "Spy Project")
    project_id = project["id"]

    sprint_1 = await _create_sprint(client, token, project_id, "Spy Sprint 1")
    sprint_2 = await _create_sprint(client, token, project_id, "Spy Sprint 2")
    sprint_3 = await _create_sprint(client, token, project_id, "Spy Sprint 3")
    await _create_task(client, token, project_id, "Spy task 1", sprint_id=sprint_1["id"])
    await _create_task(client, token, project_id, "Spy task 2", sprint_id=sprint_2["id"])
    await _create_task(client, token, project_id, "Spy task 3", sprint_id=sprint_3["id"])
    await _create_task(client, token, project_id, "Spy backlog task")

    # A plain function (not ``AsyncMock``) is used as the spy: assigning it as
    # a class attribute preserves Python's normal method-binding descriptor
    # protocol, so ``self`` is passed through correctly to the wrapped
    # original — an ``AsyncMock`` set directly on the class does NOT bind.
    original = SprintRepository.aggregate_tasks_by_sprint
    call_count = {"n": 0}

    async def _spy(self, *args, **kwargs):
        call_count["n"] += 1
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(SprintRepository, "aggregate_tasks_by_sprint", _spy)

    response = await client.get(f"/projects/{project_id}/sprints", headers=_auth(token))
    assert response.status_code == 200, response.text
    assert call_count["n"] == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sprint_read_burndown_and_close_payloads_unchanged_by_aggregates(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``SprintRead`` stays additive-only: ``burndown`` and ``close`` never
    grow ``story_count``/``estimation_hours_sum`` — those live only in the
    list item and ``meta.backlog``."""

    _, token = user
    project = await _create_scrum_project(client, token, "Contract Project")
    project_id = project["id"]

    sprint = await _create_sprint(client, token, project_id, "Contract Sprint")
    await _create_task(client, token, project_id, "Contract task", sprint_id=sprint["id"])

    burndown_response = await client.get(
        f"/projects/{project_id}/sprints/{sprint['id']}/burndown", headers=_auth(token)
    )
    assert burndown_response.status_code == 200, burndown_response.text
    burndown_sprint = burndown_response.json()["data"]["sprint"]
    assert "story_count" not in burndown_sprint
    assert "estimation_hours_sum" not in burndown_sprint

    close_response = await client.post(
        f"/sprints/{sprint['id']}/close", headers=_auth(token)
    )
    assert close_response.status_code == 200, close_response.text
    closed_sprint = close_response.json()["data"]["sprint"]
    assert "story_count" not in closed_sprint
    assert "estimation_hours_sum" not in closed_sprint
