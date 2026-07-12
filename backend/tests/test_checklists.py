"""Tests for the checklists module (change 04, Batch B).

R5 CRUD checklist · R6 CRUD/toggle/reorder ítems · R7 progreso agregado.
Uses the shared in-process fixtures (``client``/``tenant``/``user``).
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
        json={"name": "Checklist Project", "methodology": "kanban"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_task(client: AsyncClient, token: str, project_id: str) -> str:
    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Publish the release"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_checklist(
    client: AsyncClient, token: str, task_id: str, title: str
) -> dict:
    return await client.post(
        f"/tasks/{task_id}/checklists", json={"title": title}, headers=_auth(token)
    )


async def _create_item(
    client: AsyncClient, token: str, checklist_id: str, text: str
) -> dict:
    return await client.post(
        f"/checklists/{checklist_id}/items", json={"text": text}, headers=_auth(token)
    )


# ---------------------------------------------------------------------------
# T06 — RED+GREEN: CRUD checklist (R5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_checklist_returns_201_and_appears_in_listing(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Creating a checklist on a task without checklists succeeds (201) and lists it."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)

    response = await _create_checklist(client, token, task_id, "Antes de publicar")

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["title"] == "Antes de publicar"
    assert body["done"] == 0
    assert body["total"] == 0

    listing = await client.get(f"/tasks/{task_id}/checklists", headers=_auth(token))
    assert listing.json()["meta"]["total"] == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_checklist_renames_it(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """PATCH /checklists/{id} renames a checklist."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)
    created = await _create_checklist(client, token, task_id, "Borrador")
    checklist_id = created.json()["data"]["id"]

    response = await client.patch(
        f"/checklists/{checklist_id}",
        json={"title": "Antes de publicar"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["title"] == "Antes de publicar"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_checklist_removes_it_from_listing(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """DELETE /checklists/{id} soft-deletes it — it stops appearing in the listing."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)
    created = await _create_checklist(client, token, task_id, "Antes de publicar")
    checklist_id = created.json()["data"]["id"]

    delete_response = await client.delete(
        f"/checklists/{checklist_id}", headers=_auth(token)
    )
    assert delete_response.status_code == 204

    listing = await client.get(f"/tasks/{task_id}/checklists", headers=_auth(token))
    assert listing.json()["meta"]["total"] == 0


# ---------------------------------------------------------------------------
# T07 — RED+GREEN: CRUD ítems + reorder (R6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_and_list_items(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Creating items on a checklist lists them back, ordered."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)
    checklist_id = (await _create_checklist(client, token, task_id, "Checklist")).json()[
        "data"
    ]["id"]

    await _create_item(client, token, checklist_id, "Item 1")
    await _create_item(client, token, checklist_id, "Item 2")

    response = await client.get(
        f"/checklists/{checklist_id}/items", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["total"] == 2
    assert [item["text"] for item in body["data"]] == ["Item 1", "Item 2"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_item_edits_text(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """PATCH /checklist-items/{id} edits an item's text."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)
    checklist_id = (await _create_checklist(client, token, task_id, "Checklist")).json()[
        "data"
    ]["id"]
    item_id = (await _create_item(client, token, checklist_id, "Draft")).json()["data"][
        "id"
    ]

    response = await client.patch(
        f"/checklist-items/{item_id}", json={"text": "Final"}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["text"] == "Final"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reorder_items_updates_display_order(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Updating an item's ``order`` reflects the new order in the listing."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)
    checklist_id = (await _create_checklist(client, token, task_id, "Checklist")).json()[
        "data"
    ]["id"]

    item_ids = []
    for i, text in enumerate(["First", "Second", "Third"]):
        response = await client.post(
            f"/checklists/{checklist_id}/items",
            json={"text": text, "order": i},
            headers=_auth(token),
        )
        item_ids.append(response.json()["data"]["id"])

    # Move the third item ("Third", order=2) to the front (order=0);
    # the other two shift by matching PATCH calls (client-driven reorder).
    await client.patch(
        f"/checklist-items/{item_ids[2]}", json={"order": 0}, headers=_auth(token)
    )
    await client.patch(
        f"/checklist-items/{item_ids[0]}", json={"order": 1}, headers=_auth(token)
    )
    await client.patch(
        f"/checklist-items/{item_ids[1]}", json={"order": 2}, headers=_auth(token)
    )

    response = await client.get(
        f"/checklists/{checklist_id}/items", headers=_auth(token)
    )
    assert [item["text"] for item in response.json()["data"]] == [
        "Third",
        "First",
        "Second",
    ]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_item_removes_it_from_listing(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """DELETE /checklist-items/{id} soft-deletes it."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)
    checklist_id = (await _create_checklist(client, token, task_id, "Checklist")).json()[
        "data"
    ]["id"]
    item_id = (await _create_item(client, token, checklist_id, "Item")).json()["data"][
        "id"
    ]

    delete_response = await client.delete(
        f"/checklist-items/{item_id}", headers=_auth(token)
    )
    assert delete_response.status_code == 204

    listing = await client.get(
        f"/checklists/{checklist_id}/items", headers=_auth(token)
    )
    assert listing.json()["meta"]["total"] == 0


# ---------------------------------------------------------------------------
# T08 — RED+GREEN: toggle is_done (R6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_toggle_item_flips_is_done(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Toggling an item flips ``is_done`` false -> true -> false."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)
    checklist_id = (await _create_checklist(client, token, task_id, "Checklist")).json()[
        "data"
    ]["id"]
    item = (await _create_item(client, token, checklist_id, "Item")).json()["data"]
    assert item["is_done"] is False
    item_id = item["id"]

    first_toggle = await client.patch(
        f"/checklist-items/{item_id}/toggle", headers=_auth(token)
    )
    assert first_toggle.status_code == 200, first_toggle.text
    assert first_toggle.json()["data"]["is_done"] is True

    second_toggle = await client.patch(
        f"/checklist-items/{item_id}/toggle", headers=_auth(token)
    )
    assert second_toggle.json()["data"]["is_done"] is False


# ---------------------------------------------------------------------------
# T09 — RED+GREEN: get_checklist_progress (R7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_checklist_listing_reports_done_over_total(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A checklist with 5 items, 2 done, reports progress 2/5 in the listing."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)
    checklist_id = (await _create_checklist(client, token, task_id, "Checklist")).json()[
        "data"
    ]["id"]

    item_ids = []
    for i in range(5):
        response = await _create_item(client, token, checklist_id, f"Item {i}")
        item_ids.append(response.json()["data"]["id"])

    for item_id in item_ids[:2]:
        await client.patch(
            f"/checklist-items/{item_id}/toggle", headers=_auth(token)
        )

    response = await client.get(f"/tasks/{task_id}/checklists", headers=_auth(token))

    assert response.status_code == 200, response.text
    checklist = response.json()["data"][0]
    assert checklist["done"] == 2
    assert checklist["total"] == 5


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_checklist_progress_aggregates_across_checklists(
    session, tenant: Organization, user: tuple[User, str]
) -> None:
    """get_checklist_progress sums done/total across every checklist of a task (2/5 + 1/2 = 3/7)."""

    from app.modules.checklists.models import ChecklistItem, TaskChecklist
    from app.modules.checklists.service import ChecklistService
    from app.modules.projects.models import Project
    from app.modules.tasks.models import Task

    project = Project(
        organization_id=tenant.id, name="Aggregate Project", methodology="kanban",
        code="AGG1",
    )
    session.add(project)
    await session.flush()

    task = Task(project_id=project.id, title="Task", status="Backlog")
    session.add(task)
    await session.flush()

    checklist_a = TaskChecklist(
        organization_id=tenant.id, task_id=task.id, title="Checklist A"
    )
    checklist_b = TaskChecklist(
        organization_id=tenant.id, task_id=task.id, title="Checklist B"
    )
    session.add_all([checklist_a, checklist_b])
    await session.flush()

    # Checklist A: 5 items, 2 done.
    for i in range(5):
        session.add(
            ChecklistItem(
                organization_id=tenant.id,
                checklist_id=checklist_a.id,
                text=f"A{i}",
                is_done=i < 2,
            )
        )
    # Checklist B: 2 items, 1 done.
    for i in range(2):
        session.add(
            ChecklistItem(
                organization_id=tenant.id,
                checklist_id=checklist_b.id,
                text=f"B{i}",
                is_done=i < 1,
            )
        )
    await session.flush()

    service = ChecklistService(session)
    done, total = await service.get_checklist_progress(task.id)

    assert (done, total) == (3, 7)
