"""Tests for ``POST /tasks/reorder`` — reordenamiento transaccional.

Mueve ``task_id`` a ``sprint_id`` (o ``null`` = Backlog) y reindexa el campo
``order`` de todas las tareas del contenedor destino según
``ordered_task_ids``, en una sola transacción (design.md D1;
openspec/changes/31-backlog-drag-drop/specs/tasks/spec.md, "Reordenamiento
transaccional vía POST /tasks/reorder"). Aplica el mismo guard de ``closed``
que ``PATCH /tasks/{id}`` (D3). El campo ``order`` NO genera entradas de
``TaskHistory`` (no está en ``_HISTORY_TRACKED_FIELDS``); solo un cambio
efectivo de ``sprint_id`` genera una fila de historial.
"""

import uuid as uuid_module

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: AsyncClient, token: str, methodology: str = "scrum") -> str:
    response = await client.post(
        "/projects",
        json={"name": f"{methodology.title()} Reorder Project", "methodology": methodology},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _seed_sprint(session, project_id: str, *, status: str = "draft") -> str:
    from app.modules.sprints.models import Sprint

    sprint = Sprint(
        project_id=uuid_module.UUID(project_id), name=f"Sprint {status}", status=status
    )
    session.add(sprint)
    await session.flush()
    return str(sprint.id)


async def _create_task(
    client: AsyncClient, token: str, project_id: str, title: str, *, sprint_id: str | None = None
) -> str:
    payload: dict[str, object] = {"title": title}
    if sprint_id is not None:
        payload["sprint_id"] = sprint_id
    response = await client.post(
        f"/projects/{project_id}/tasks", json=payload, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


# ---------------------------------------------------------------------------
# Happy path: mueve y reindexa el contenedor destino (RED)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reorder_moves_task_and_reindexes_destination_container(
    client: AsyncClient, session, tenant, user
) -> None:
    """Sprint destino ``draft`` con tareas ``[A,B,C]`` (order 0,1,2) + tarea
    ``D`` en Backlog. Tras ``POST /tasks/reorder`` insertando ``D`` entre
    ``A`` y ``B``, ``D.sprint_id`` queda asignado y el ``order`` final de
    ``A,D,B,C`` es ``0,1,2,3``."""

    _, token = user
    project_id = await _create_project(client, token)
    draft_sprint_id = await _seed_sprint(session, project_id, status="draft")

    task_a = await _create_task(client, token, project_id, "A", sprint_id=draft_sprint_id)
    task_b = await _create_task(client, token, project_id, "B", sprint_id=draft_sprint_id)
    task_c = await _create_task(client, token, project_id, "C", sprint_id=draft_sprint_id)
    task_d = await _create_task(client, token, project_id, "D")

    response = await client.post(
        "/tasks/reorder",
        json={
            "task_id": task_d,
            "sprint_id": draft_sprint_id,
            "ordered_task_ids": [task_a, task_d, task_b, task_c],
        },
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["sprint_id"] == draft_sprint_id

    listing = await client.get(
        f"/projects/{project_id}/tasks",
        params={"sprint_id": draft_sprint_id},
        headers=_auth(token),
    )
    order_by_id = {row["id"]: row["order"] for row in listing.json()["data"]}
    assert order_by_id[task_a] == 0
    assert order_by_id[task_d] == 1
    assert order_by_id[task_b] == 2
    assert order_by_id[task_c] == 3


# ---------------------------------------------------------------------------
# Guard closed (RED)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reorder_rejects_closed_target_sprint_422(
    client: AsyncClient, session, tenant, user
) -> None:
    """Destino ``closed`` responde ``422 sprint_closed``; la tarea conserva
    su ``sprint_id``/``order`` previos y ningún otro id del arreglo se toca."""

    _, token = user
    project_id = await _create_project(client, token)
    closed_sprint_id = await _seed_sprint(session, project_id, status="closed")

    task_d = await _create_task(client, token, project_id, "D")

    response = await client.post(
        "/tasks/reorder",
        json={
            "task_id": task_d,
            "sprint_id": closed_sprint_id,
            "ordered_task_ids": [task_d],
        },
        headers=_auth(token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "sprint_closed"

    detail = await client.get(f"/tasks/{task_d}", headers=_auth(token))
    assert detail.json()["data"]["sprint_id"] is None
    assert detail.json()["data"]["order"] == 0


# ---------------------------------------------------------------------------
# Aislamiento de organización (RED)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reorder_rejects_task_from_other_organization_404(
    client: AsyncClient, session, two_orgs: TwoOrgs
) -> None:
    """``task_id`` de ``two_orgs.b`` con token de ``two_orgs.a`` responde
    ``404``, sin ninguna reasignación."""

    draft_sprint_id = await _seed_sprint(
        session, str(two_orgs.a.project.id), status="draft"
    )

    response = await client.post(
        "/tasks/reorder",
        json={
            "task_id": str(two_orgs.b.task.id),
            "sprint_id": draft_sprint_id,
            "ordered_task_ids": [str(two_orgs.b.task.id)],
        },
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# Permisos existentes (RED)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reorder_respects_existing_permissions(
    client: AsyncClient, session, tenant, user
) -> None:
    """Un ``member`` reordena dentro de su proyecto (200); sin token, 401."""

    _, token = user
    project_id = await _create_project(client, token)
    draft_sprint_id = await _seed_sprint(session, project_id, status="draft")
    task_a = await _create_task(client, token, project_id, "A")

    authorized = await client.post(
        "/tasks/reorder",
        json={
            "task_id": task_a,
            "sprint_id": draft_sprint_id,
            "ordered_task_ids": [task_a],
        },
        headers=_auth(token),
    )
    assert authorized.status_code == 200, authorized.text

    unauthenticated = await client.post(
        "/tasks/reorder",
        json={
            "task_id": task_a,
            "sprint_id": draft_sprint_id,
            "ordered_task_ids": [task_a],
        },
    )
    assert unauthenticated.status_code == 401, unauthenticated.text


# ---------------------------------------------------------------------------
# Una sola transacción; order no genera TaskHistory (RED)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reorder_is_single_transaction_and_order_not_history_tracked(
    client: AsyncClient, session, monkeypatch, tenant, user
) -> None:
    """El drop hace UN solo ``TaskRepository.save`` (una transacción) y solo
    una fila nueva de ``TaskHistory`` (el cambio de ``sprint_id``); el
    reindexado de ``order`` de los hermanos NO genera historial."""

    from app.modules.activity.models import TaskHistory
    from app.modules.tasks.repository import TaskRepository

    _, token = user
    project_id = await _create_project(client, token)
    draft_sprint_id = await _seed_sprint(session, project_id, status="draft")

    task_a = await _create_task(client, token, project_id, "A", sprint_id=draft_sprint_id)
    task_b = await _create_task(client, token, project_id, "B", sprint_id=draft_sprint_id)
    task_d = await _create_task(client, token, project_id, "D")

    save_calls = 0
    original_save = TaskRepository.save

    async def _spy_save(self, task):
        nonlocal save_calls
        save_calls += 1
        return await original_save(self, task)

    monkeypatch.setattr(TaskRepository, "save", _spy_save)

    before = await session.execute(
        select(TaskHistory).where(TaskHistory.task_id == uuid_module.UUID(task_d))
    )
    assert len(before.scalars().all()) == 0

    response = await client.post(
        "/tasks/reorder",
        json={
            "task_id": task_d,
            "sprint_id": draft_sprint_id,
            "ordered_task_ids": [task_a, task_d, task_b],
        },
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    assert save_calls == 1

    after = await session.execute(
        select(TaskHistory).where(TaskHistory.task_id == uuid_module.UUID(task_d))
    )
    rows = after.scalars().all()
    assert len(rows) == 1
    assert rows[0].field == "sprint_id"
