"""Tests for advanced filters on ``GET /projects/{id}/tasks`` (change 10-busqueda-global).

R7 filtros combinables (``priority``, ``label_id`` multi, rango de fechas,
``q``) · R8 validación 422 de filtros inválidos.
"""

import pytest
from httpx import AsyncClient

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(
    client: AsyncClient, token: str, name: str = "Filter Project"
) -> str:
    response = await client.post(
        "/projects", json={"name": name, "methodology": "kanban"}, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_task(
    client: AsyncClient, token: str, project_id: str, title: str, **extra: object
) -> dict:
    payload: dict = {"title": title, **extra}
    response = await client.post(
        f"/projects/{project_id}/tasks", json=payload, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_label(
    client: AsyncClient, token: str, project_id: str, name: str
) -> dict:
    response = await client.post(
        f"/projects/{project_id}/labels",
        json={"name": name, "color": "#FF0000"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _assign_label(
    client: AsyncClient, token: str, task_id: str, label_id: str
) -> None:
    response = await client.post(
        f"/tasks/{task_id}/labels", json={"label_id": label_id}, headers=_auth(token)
    )
    assert response.status_code == 201, response.text


async def _list_tasks(client: AsyncClient, token: str, project_id: str, **params: object):
    return await client.get(
        f"/projects/{project_id}/tasks", params=params, headers=_auth(token)
    )


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_combined_filters_match_all_criteria_simultaneously(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``status+priority+assignee_id+label_id+due_from+due_to`` narrows to the
    single task that satisfies every criterion at once (R7).
    """

    owner, token = user
    project_id = await _create_project(client, token)
    label = await _create_label(client, token, project_id, "Urgente")

    matching = await _create_task(
        client,
        token,
        project_id,
        "Tarea que cumple todo",
        priority="high",
        assignee_id=str(owner.id),
        due_date="2026-07-15T00:00:00Z",
    )
    await _assign_label(client, token, matching["id"], label["id"])

    # Distractor: identical (same label too) except priority — must be
    # excluded by the AND, isolating the priority filter specifically.
    distractor = await _create_task(
        client,
        token,
        project_id,
        "Tarea con otra prioridad",
        priority="low",
        assignee_id=str(owner.id),
        due_date="2026-07-15T00:00:00Z",
    )
    await _assign_label(client, token, distractor["id"], label["id"])

    response = await _list_tasks(
        client,
        token,
        project_id,
        status="Backlog",
        priority="high",
        assignee_id=str(owner.id),
        label_id=label["id"],
        due_from="2026-07-01",
        due_to="2026-07-31",
    )

    assert response.status_code == 200, response.text
    ids = [t["id"] for t in response.json()["data"]]
    assert ids == [matching["id"]]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_label_id_multiple_values_uses_or_semantics_without_duplicates(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``label_id`` repeated matches ANY of the given labels, no duplicates (R7)."""

    _, token = user
    project_id = await _create_project(client, token)
    urgente = await _create_label(client, token, project_id, "Urgente")
    backend = await _create_label(client, token, project_id, "Backend")

    task_urgente = await _create_task(client, token, project_id, "Solo urgente")
    await _assign_label(client, token, task_urgente["id"], urgente["id"])

    task_backend = await _create_task(client, token, project_id, "Solo backend")
    await _assign_label(client, token, task_backend["id"], backend["id"])

    task_both = await _create_task(client, token, project_id, "Ambas etiquetas")
    await _assign_label(client, token, task_both["id"], urgente["id"])
    await _assign_label(client, token, task_both["id"], backend["id"])

    task_neither = await _create_task(client, token, project_id, "Sin etiqueta")

    response = await _list_tasks(
        client, token, project_id, label_id=[urgente["id"], backend["id"]]
    )

    assert response.status_code == 200, response.text
    ids = [t["id"] for t in response.json()["data"]]
    assert set(ids) == {task_urgente["id"], task_backend["id"], task_both["id"]}
    assert task_neither["id"] not in ids
    assert ids.count(task_both["id"]) == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_q_filter_matches_title_or_description(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``q`` matches a term present in either ``title`` or ``description`` (R7)."""

    _, token = user
    project_id = await _create_project(client, token)

    title_match = await _create_task(client, token, project_id, "Migrar base de datos")
    description_match = await _create_task(
        client,
        token,
        project_id,
        "Tarea genérica",
        description="Requiere migrar el esquema legado.",
    )
    unrelated = await _create_task(client, token, project_id, "Actualizar dependencias")

    response = await _list_tasks(client, token, project_id, q="migrar")

    assert response.status_code == 200, response.text
    ids = {t["id"] for t in response.json()["data"]}
    assert ids == {title_match["id"], description_match["id"]}
    assert unrelated["id"] not in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_due_date_range_filters_tasks_within_bounds(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``due_from``/``due_to`` keeps only tasks with ``due_date`` inside the range (R7)."""

    _, token = user
    project_id = await _create_project(client, token)

    in_range = await _create_task(
        client, token, project_id, "Tarea de julio", due_date="2026-07-15T00:00:00Z"
    )
    out_of_range = await _create_task(
        client, token, project_id, "Tarea de junio", due_date="2026-06-10T00:00:00Z"
    )
    no_due_date = await _create_task(client, token, project_id, "Tarea sin fecha")

    response = await _list_tasks(
        client, token, project_id, due_from="2026-07-01", due_to="2026-07-31"
    )

    assert response.status_code == 200, response.text
    ids = [t["id"] for t in response.json()["data"]]
    assert ids == [in_range["id"]]
    assert out_of_range["id"] not in ids
    assert no_due_date["id"] not in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_priority_out_of_catalog_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A ``priority`` value outside the catalog is rejected (R8)."""

    _, token = user
    project_id = await _create_project(client, token)

    response = await _list_tasks(client, token, project_id, priority="urgentísima")

    assert response.status_code == 422, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_due_from_after_due_to_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """An inverted date range (``due_from > due_to``) is rejected (R8)."""

    _, token = user
    project_id = await _create_project(client, token)

    response = await _list_tasks(
        client, token, project_id, due_from="2026-07-31", due_to="2026-07-01"
    )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_filters_combine_with_standard_pagination_meta(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Filters compose with the standard opt-in pagination of 02-contrato-api."""

    _, token = user
    project_id = await _create_project(client, token)
    await _create_task(client, token, project_id, "Tarea A", priority="high")
    await _create_task(client, token, project_id, "Tarea B", priority="high")
    await _create_task(client, token, project_id, "Tarea C", priority="low")

    response = await _list_tasks(
        client, token, project_id, priority="high", page=1, size=1, sort="title"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"] == {"page": 1, "size": 1, "total": 2}
    assert len(body["data"]) == 1


# ---------------------------------------------------------------------------
# Filtros task_type y parent_task_id (habilitadores UX de jerarquía)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_filter_by_task_type_returns_only_matching_type(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``?task_type=epic`` returns ONLY the epics of the project."""

    _, token = user
    project_id = await _create_project(client, token, "Task Type Filter Project")
    epic = await _create_task(client, token, project_id, "Épica", task_type="epic")
    await _create_task(client, token, project_id, "Tarea Normal")
    await _create_task(client, token, project_id, "Bug", task_type="bug")

    response = await _list_tasks(client, token, project_id, task_type="epic")

    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert [row["id"] for row in rows] == [epic["id"]]
    assert all(row["task_type"] == "epic" for row in rows)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_filter_by_parent_task_id_returns_epic_children(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``?parent_task_id=<epic>`` returns the epic's children — normally
    hidden from the top-level listing."""

    _, token = user
    project_id = await _create_project(client, token, "Parent Filter Project")
    epic = await _create_task(client, token, project_id, "Épica Padre", task_type="epic")
    child_a = await _create_task(
        client, token, project_id, "Historia A",
        task_type="story", parent_task_id=epic["id"],
    )
    child_b = await _create_task(
        client, token, project_id, "Historia B",
        task_type="story", parent_task_id=epic["id"],
    )
    await _create_task(client, token, project_id, "Tarea Suelta")

    response = await _list_tasks(
        client, token, project_id, parent_task_id=epic["id"]
    )

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert ids == {child_a["id"], child_b["id"]}

    # Sin el filtro, el listado sigue siendo solo de tareas top-level.
    unfiltered = await _list_tasks(client, token, project_id)
    top_ids = {row["id"] for row in unfiltered.json()["data"]}
    assert child_a["id"] not in top_ids
    assert epic["id"] in top_ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_type_filter_combines_with_existing_filters(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``task_type`` composes with the pre-existing filters (``priority``)."""

    _, token = user
    project_id = await _create_project(client, token, "Combined Type Filter Project")
    epic_high = await _create_task(
        client, token, project_id, "Épica Alta", task_type="epic", priority="high"
    )
    await _create_task(
        client, token, project_id, "Épica Media", task_type="epic", priority="medium"
    )
    await _create_task(
        client, token, project_id, "Tarea Alta", priority="high"
    )

    response = await _list_tasks(
        client, token, project_id, task_type="epic", priority="high"
    )

    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert [row["id"] for row in rows] == [epic_high["id"]]
