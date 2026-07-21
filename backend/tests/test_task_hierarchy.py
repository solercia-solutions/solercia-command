"""Tests for hierarchical task listing and the assignee-context rule
(change 32-jerarquia-subtareas).

``GET /projects/{id}/tasks``:

- ``include_subtasks=true`` lifts the top-level-only restriction, returning
  a flat listing (top-level + subtasks) in the existing ``order asc,
  created_at asc`` order, without nesting them into a tree.
- Non-negotiable rule: with ``assignee_id`` present (with or without
  ``include_subtasks``), any subtask assigned to that user MUST appear even
  when its parent is assigned to someone else or does not itself match the
  filter. That foreign parent is returned too, flagged ``is_context=true``,
  deduplicated when the parent already matches the filter by itself
  (``is_context=false``). Context parents never count in ``meta.total``.
"""

import pytest
from httpx import AsyncClient

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(
    client: AsyncClient, token: str, name: str = "Hierarchy Project"
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


async def _list_tasks(client: AsyncClient, token: str, project_id: str, **params: object):
    return await client.get(
        f"/projects/{project_id}/tasks", params=params, headers=_auth(token)
    )


# ---------------------------------------------------------------------------
# include_subtasks levanta top_level_only (1.1, 1.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_default_listing_stays_top_level_only_no_regression(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Sin ``include_subtasks`` ni ``assignee_id``, el listado sigue siendo
    exclusivamente de nivel superior — igual que antes de este cambio."""

    _, token = user
    project_id = await _create_project(client, token)
    parent = await _create_task(client, token, project_id, "Tarea Padre")
    await _create_task(
        client, token, project_id, "Subtarea 1", parent_task_id=parent["id"]
    )
    await _create_task(
        client, token, project_id, "Subtarea 2", parent_task_id=parent["id"]
    )

    response = await _list_tasks(client, token, project_id)

    assert response.status_code == 200, response.text
    ids = [row["id"] for row in response.json()["data"]]
    assert ids == [parent["id"]]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_include_subtasks_true_returns_top_level_and_subtasks_flat(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``include_subtasks=true`` incluye padre + subtareas, listado plano en
    ``order asc, created_at asc``, sin anidarlas en un árbol."""

    _, token = user
    project_id = await _create_project(client, token)
    parent = await _create_task(client, token, project_id, "Tarea Padre")
    sub_a = await _create_task(
        client, token, project_id, "Subtarea A", parent_task_id=parent["id"]
    )
    sub_b = await _create_task(
        client, token, project_id, "Subtarea B", parent_task_id=parent["id"]
    )

    response = await _list_tasks(client, token, project_id, include_subtasks="true")

    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    ids = [row["id"] for row in rows]
    assert ids == [parent["id"], sub_a["id"], sub_b["id"]]
    assert all("subtasks" not in row for row in rows)


# ---------------------------------------------------------------------------
# Regla innegociable: subtarea de padre ajeno visible al filtrar por
# asignado (1.3, 1.4, 1.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_assignee_filter_surfaces_subtask_of_foreign_parent_without_include_subtasks(
    client: AsyncClient, tenant: Organization, user: tuple[User, str], make_member, session
) -> None:
    """Una subtarea asignada a A cuyo padre está asignado a B aparece al
    filtrar por A (SIN ``include_subtasks``), y el padre de B se devuelve
    también, marcado ``is_context=true``."""

    from app.shared.enums import MemberRole

    user_a, token_a = user
    user_b, _token_b = await make_member(session, tenant, MemberRole.member)

    project_id = await _create_project(client, token_a)
    parent_of_b = await _create_task(
        client, token_a, project_id, "Tarea Padre de B", assignee_id=str(user_b.id)
    )
    subtask_of_a = await _create_task(
        client,
        token_a,
        project_id,
        "Subtarea de A",
        parent_task_id=parent_of_b["id"],
        assignee_id=str(user_a.id),
    )

    response = await _list_tasks(
        client, token_a, project_id, assignee_id=str(user_a.id)
    )

    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    ids_to_row = {row["id"]: row for row in rows}
    assert subtask_of_a["id"] in ids_to_row
    assert parent_of_b["id"] in ids_to_row
    assert ids_to_row[parent_of_b["id"]]["is_context"] is True


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_context_parent_not_duplicated_when_it_also_matches_assignee(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Cuando el padre TAMBIÉN está asignado a A, aparece una sola vez, con
    ``is_context=false`` (no se reinyecta como contexto)."""

    user_a, token_a = user
    project_id = await _create_project(client, token_a)
    parent_of_a = await _create_task(
        client, token_a, project_id, "Tarea Padre de A", assignee_id=str(user_a.id)
    )
    await _create_task(
        client,
        token_a,
        project_id,
        "Subtarea de A",
        parent_task_id=parent_of_a["id"],
        assignee_id=str(user_a.id),
    )

    response = await _list_tasks(
        client, token_a, project_id, assignee_id=str(user_a.id)
    )

    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    parent_rows = [row for row in rows if row["id"] == parent_of_a["id"]]
    assert len(parent_rows) == 1
    assert parent_rows[0]["is_context"] is False


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_meta_total_excludes_context_parent(
    client: AsyncClient, tenant: Organization, user: tuple[User, str], make_member, session
) -> None:
    """3 matches reales (2 top-level + 1 subtarea, todos asignados a A) más 1
    padre de contexto (asignado a B) no cuentan en ``meta.total``, pero SÍ
    aparecen en ``data`` (4 filas en total)."""

    from app.shared.enums import MemberRole

    user_a, token_a = user
    user_b, _token_b = await make_member(session, tenant, MemberRole.member)

    project_id = await _create_project(client, token_a)
    top_1 = await _create_task(
        client, token_a, project_id, "Top 1 de A", assignee_id=str(user_a.id)
    )
    top_2 = await _create_task(
        client, token_a, project_id, "Top 2 de A", assignee_id=str(user_a.id)
    )
    parent_of_b = await _create_task(
        client, token_a, project_id, "Padre de B", assignee_id=str(user_b.id)
    )
    subtask_of_a = await _create_task(
        client,
        token_a,
        project_id,
        "Subtarea de A con padre ajeno",
        parent_task_id=parent_of_b["id"],
        assignee_id=str(user_a.id),
    )

    response = await _list_tasks(
        client, token_a, project_id, assignee_id=str(user_a.id)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["total"] == 3
    ids = {row["id"] for row in body["data"]}
    assert ids == {top_1["id"], top_2["id"], parent_of_b["id"], subtask_of_a["id"]}
    assert len(body["data"]) == 4


# ---------------------------------------------------------------------------
# Campo aditivo is_context (1.6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_is_context_defaults_false_without_assignee_filter(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Sin ``assignee_id``, toda fila trae ``is_context=false`` — es un campo
    aditivo que nunca se activa fuera del filtro por asignado."""

    _, token = user
    project_id = await _create_project(client, token)
    parent = await _create_task(client, token, project_id, "Tarea Padre")
    await _create_task(
        client, token, project_id, "Subtarea", parent_task_id=parent["id"]
    )

    plain = await _list_tasks(client, token, project_id)
    assert plain.status_code == 200, plain.text
    assert all(row["is_context"] is False for row in plain.json()["data"])

    with_subtasks = await _list_tasks(
        client, token, project_id, include_subtasks="true"
    )
    assert with_subtasks.status_code == 200, with_subtasks.text
    rows = with_subtasks.json()["data"]
    assert len(rows) == 2
    assert all(row["is_context"] is False for row in rows)


# ---------------------------------------------------------------------------
# Permisos y aislamiento multi-tenant (1.7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_hierarchy_and_context_respect_tenant_scoping_and_auth(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """Un ``member`` autenticado consulta su propio proyecto (200); sin
    token responde 401; un proyecto de otra organización responde 404."""

    own_project_id = str(two_orgs.a.project.id)
    foreign_project_id = str(two_orgs.b.project.id)
    a_user_id = str(two_orgs.a.user.id)

    authorized = await _list_tasks(
        client,
        two_orgs.a.token,
        own_project_id,
        include_subtasks="true",
        assignee_id=a_user_id,
    )
    assert authorized.status_code == 200, authorized.text

    unauthenticated = await client.get(
        f"/projects/{own_project_id}/tasks",
        params={"include_subtasks": "true", "assignee_id": a_user_id},
    )
    assert unauthenticated.status_code == 401, unauthenticated.text

    foreign = await _list_tasks(
        client,
        two_orgs.a.token,
        foreign_project_id,
        include_subtasks="true",
        assignee_id=a_user_id,
    )
    assert foreign.status_code == 404, foreign.text
