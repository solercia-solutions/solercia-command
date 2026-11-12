"""Tests for the ``closed``-sprint guard on ``PATCH /tasks/{id}``.

`_verify_sprint` (service.py) hoy solo valida que el sprint EXISTE en el
proyecto; no valida su ``status``. Este archivo cubre el requisito ADDED
"Guard de integridad al asignar sprint_id en PATCH"
(openspec/changes/31-backlog-drag-drop/specs/tasks/spec.md): mover una tarea
hacia un sprint ``closed`` vía ``PATCH /tasks/{id}`` DEBE responder ``422``
con ``code=sprint_closed`` y conservar el ``sprint_id`` anterior de la tarea;
``draft``/``active`` siguen aceptándose sin restricción adicional.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: AsyncClient, token: str, methodology: str = "scrum") -> str:
    response = await client.post(
        "/projects",
        json={"name": f"{methodology.title()} Guard Project", "methodology": methodology},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _seed_sprint(session, project_id: str, *, status: str) -> str:
    """Seed a ``Sprint`` directly with the given ``status`` (no API path to
    create a ``closed`` sprint from scratch, so it is inserted directly)."""

    import uuid as uuid_module

    from app.modules.sprints.models import Sprint

    sprint = Sprint(project_id=uuid_module.UUID(project_id), name=f"Sprint {status}", status=status)
    session.add(sprint)
    await session.flush()
    return str(sprint.id)


# ---------------------------------------------------------------------------
# Guard: PATCH hacia un sprint closed se rechaza (RED)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_task_rejects_closed_target_sprint_422(
    client: AsyncClient, session, tenant, user
) -> None:
    """Una tarea en el Backlog no puede moverse a un sprint ``closed`` vía
    ``PATCH /tasks/{id}``; la respuesta es ``422`` con ``code=sprint_closed``
    y la tarea conserva su ``sprint_id`` anterior (``None``, Backlog)."""

    _, token = user
    project_id = await _create_project(client, token)
    closed_sprint_id = await _seed_sprint(session, project_id, status="closed")

    task = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Backlog task"},
        headers=_auth(token),
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["data"]["id"]

    response = await client.patch(
        f"/tasks/{task_id}",
        json={"sprint_id": closed_sprint_id},
        headers=_auth(token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "sprint_closed"

    detail = await client.get(f"/tasks/{task_id}", headers=_auth(token))
    assert detail.json()["data"]["sprint_id"] is None


# ---------------------------------------------------------------------------
# No-regresión: draft/active se siguen aceptando (ya verde hoy)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_task_accepts_draft_and_active_target_sprint(
    client: AsyncClient, session, tenant, user
) -> None:
    """``draft`` y ``active`` se aceptan sin exigir que origen y destino
    compartan estado (spec Escenarios 1/2)."""

    _, token = user
    project_id = await _create_project(client, token)
    draft_sprint_id = await _seed_sprint(session, project_id, status="draft")
    active_sprint_id = await _seed_sprint(session, project_id, status="active")

    task = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Backlog task"},
        headers=_auth(token),
    )
    task_id = task.json()["data"]["id"]

    to_draft = await client.patch(
        f"/tasks/{task_id}",
        json={"sprint_id": draft_sprint_id},
        headers=_auth(token),
    )
    assert to_draft.status_code == 200, to_draft.text
    assert to_draft.json()["data"]["sprint_id"] == draft_sprint_id

    to_active = await client.patch(
        f"/tasks/{task_id}",
        json={"sprint_id": active_sprint_id},
        headers=_auth(token),
    )
    assert to_active.status_code == 200, to_active.text
    assert to_active.json()["data"]["sprint_id"] == active_sprint_id


# ---------------------------------------------------------------------------
# Permisos y aislamiento de organización (ya verde hoy)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_task_sprint_guard_respects_permissions_and_org_isolation(
    client: AsyncClient, session, two_orgs: TwoOrgs
) -> None:
    """Un ``member`` reasigna su propio sprint ``draft`` sin restricción
    nueva de rol; un ``sprint_id`` de otra organización se rechaza sin
    reasignar nada (aislamiento preservado).

    Nota de reconciliación: ``specs/tasks/spec.md`` describe este escenario
    como ``404``, pero el comportamiento YA existente de
    ``TaskService._verify_sprint`` (sin cambios en este alcance — D3 solo
    añade el guard de ``closed``) responde ``422`` ``code=invalid_sprint``
    para cualquier sprint no encontrado en el org/proyecto del solicitante,
    sin distinguir "no existe" de "pertenece a otra organización". El
    resultado protector es el mismo (nunca se reasigna un sprint ajeno);
    ampliar `_verify_sprint` para diferenciar 404 está fuera del alcance de
    esta reconciliación (D3, guard mínimo)."""

    draft_sprint_id = await _seed_sprint(
        session, str(two_orgs.a.project.id), status="draft"
    )
    same_org = await client.patch(
        f"/tasks/{two_orgs.a.task.id}",
        json={"sprint_id": draft_sprint_id},
        headers=_auth(two_orgs.a.token),
    )
    assert same_org.status_code == 200, same_org.text

    other_org_sprint_id = await _seed_sprint(
        session, str(two_orgs.b.project.id), status="draft"
    )
    cross_org = await client.patch(
        f"/tasks/{two_orgs.a.task.id}",
        json={"sprint_id": other_org_sprint_id},
        headers=_auth(two_orgs.a.token),
    )
    assert cross_org.status_code == 422, cross_org.text
    assert cross_org.json()["code"] == "invalid_sprint"
    detail = await client.get(
        f"/tasks/{two_orgs.a.task.id}", headers=_auth(two_orgs.a.token)
    )
    assert detail.json()["data"]["sprint_id"] == draft_sprint_id
