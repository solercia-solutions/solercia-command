"""Tests for task detail enrichment (change 04, Batch E — T23/T24).

T23: labels[] + checklist_progress populate on single-task reads (mirrors
subtask_progress). T24: GET /tasks/{id} exposes labels[], checklist_progress,
is_blocked and blockers[] SIMULTANEOUSLY, in one integration test.
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
        json={"name": "Enrichment Project", "methodology": "kanban"},
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


# ---------------------------------------------------------------------------
# T23 — labels[] populates on single-task reads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_detail_reports_assigned_labels(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """GET /tasks/{id} lists the task's active labels."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id, "Labeled task")

    label_response = await client.post(
        f"/projects/{project_id}/labels",
        json={"name": "Urgente", "color": "#FF0000"},
        headers=_auth(token),
    )
    label_id = label_response.json()["data"]["id"]
    await client.post(
        f"/tasks/{task_id}/labels", json={"label_id": label_id}, headers=_auth(token)
    )

    response = await client.get(f"/tasks/{task_id}", headers=_auth(token))

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert [label["id"] for label in body["labels"]] == [label_id]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_detail_no_labels_reports_empty_list(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A task with no labels assigned reports an empty labels[]."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id, "Unlabeled task")

    response = await client.get(f"/tasks/{task_id}", headers=_auth(token))

    assert response.json()["data"]["labels"] == []


# ---------------------------------------------------------------------------
# T23 — checklist_progress aggregates on single-task reads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_detail_reports_aggregate_checklist_progress(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """checklist_progress = done/total aggregated across every checklist (3/7 -> ~0.4286)."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id, "Checklist task")

    checklist_a = (
        await client.post(
            f"/tasks/{task_id}/checklists", json={"title": "A"}, headers=_auth(token)
        )
    ).json()["data"]["id"]
    checklist_b = (
        await client.post(
            f"/tasks/{task_id}/checklists", json={"title": "B"}, headers=_auth(token)
        )
    ).json()["data"]["id"]

    # Checklist A: 5 items, 2 done.
    item_ids_a = []
    for i in range(5):
        r = await client.post(
            f"/checklists/{checklist_a}/items",
            json={"text": f"A{i}"},
            headers=_auth(token),
        )
        item_ids_a.append(r.json()["data"]["id"])
    for item_id in item_ids_a[:2]:
        await client.patch(f"/checklist-items/{item_id}/toggle", headers=_auth(token))

    # Checklist B: 2 items, 1 done.
    item_ids_b = []
    for i in range(2):
        r = await client.post(
            f"/checklists/{checklist_b}/items",
            json={"text": f"B{i}"},
            headers=_auth(token),
        )
        item_ids_b.append(r.json()["data"]["id"])
    await client.patch(f"/checklist-items/{item_ids_b[0]}/toggle", headers=_auth(token))

    response = await client.get(f"/tasks/{task_id}", headers=_auth(token))

    assert response.status_code == 200, response.text
    progress = response.json()["data"]["checklist_progress"]
    assert progress == pytest.approx(3 / 7)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_detail_no_checklist_items_progress_is_null(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A task with no checklist items reports checklist_progress=null."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id, "No checklist task")

    response = await client.get(f"/tasks/{task_id}", headers=_auth(token))

    assert response.json()["data"]["checklist_progress"] is None


# ---------------------------------------------------------------------------
# T24 — Integration: all four fields exposed SIMULTANEOUSLY (single test)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_detail_exposes_all_enrichment_simultaneously(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """GET /tasks/{id} reports labels[], checklist_progress, is_blocked and
    blockers[] all at once, on the SAME response — the real integration
    surface a frontend detail view would consume in one request.
    """

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id, "Fully enriched task")
    blocker_id = await _create_task(client, token, project_id, "Blocker task")

    # Label.
    label_id = (
        await client.post(
            f"/projects/{project_id}/labels",
            json={"name": "Bloqueante", "color": "#000000"},
            headers=_auth(token),
        )
    ).json()["data"]["id"]
    await client.post(
        f"/tasks/{task_id}/labels", json={"label_id": label_id}, headers=_auth(token)
    )

    # Checklist with one done item out of two.
    checklist_id = (
        await client.post(
            f"/tasks/{task_id}/checklists",
            json={"title": "Pre-lanzamiento"},
            headers=_auth(token),
        )
    ).json()["data"]["id"]
    item_ids = []
    for i in range(2):
        r = await client.post(
            f"/checklists/{checklist_id}/items",
            json={"text": f"Item {i}"},
            headers=_auth(token),
        )
        item_ids.append(r.json()["data"]["id"])
    await client.patch(f"/checklist-items/{item_ids[0]}/toggle", headers=_auth(token))

    # Dependency: this task is blocked by `blocker_id`.
    await client.post(
        f"/tasks/{task_id}/dependencies",
        json={"related_task_id": blocker_id, "type": "is_blocked_by"},
        headers=_auth(token),
    )

    response = await client.get(f"/tasks/{task_id}", headers=_auth(token))

    assert response.status_code == 200, response.text
    body = response.json()["data"]

    assert [label["id"] for label in body["labels"]] == [label_id]
    assert body["checklist_progress"] == pytest.approx(0.5)
    assert body["is_blocked"] is True
    assert [blocker["task_id"] for blocker in body["blockers"]] == [blocker_id]
