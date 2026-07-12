"""Tests for the global search module (change 10-busqueda-global).

R1 contrato del endpoint · R2 longitud mínima de ``q`` · R3 validación de
``types`` · R4 scope estricto por organización · R5 exclusión de borrado
suave · R6 permisos sin restricción de rol.
"""

import re
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(
    client: AsyncClient,
    token: str,
    name: str = "Search Project",
    *,
    description: str | None = None,
    methodology: str = "kanban",
) -> dict:
    payload: dict = {"name": name, "methodology": methodology}
    if description is not None:
        payload["description"] = description
    response = await client.post("/projects", json=payload, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_task(
    client: AsyncClient,
    token: str,
    project_id: str,
    title: str,
    *,
    description: str | None = None,
) -> dict:
    payload: dict = {"title": title}
    if description is not None:
        payload["description"] = description
    response = await client.post(
        f"/projects/{project_id}/tasks", json=payload, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_comment(
    client: AsyncClient, token: str, task_id: str, body: str
) -> dict:
    response = await client.post(
        f"/tasks/{task_id}/comments", json={"body": body}, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _search(client: AsyncClient, token: str, **params: str):
    return await client.get("/search", params=params, headers=_auth(token))

# ---------------------------------------------------------------------------
# T06 — RED: pure unit tests (no DB) for the LIKE-escape and ``types`` CSV
# parsing helpers. Fails on collection while `app.modules.search.schemas`
# does not exist yet.
# ---------------------------------------------------------------------------


def test_escape_like_escapes_percent_underscore_backslash() -> None:
    """``%``, ``_`` and ``\\`` are escaped so they act as literal characters."""

    from app.modules.search.schemas import escape_like

    assert escape_like("100%_done\\now") == "100\\%\\_done\\\\now"


def test_escape_like_leaves_plain_text_untouched() -> None:
    """A query with no LIKE metacharacters passes through unchanged."""

    from app.modules.search.schemas import escape_like

    assert escape_like("factura") == "factura"


def test_parse_types_default_returns_all_three_entities() -> None:
    """Omitting ``types`` (``None``) returns the full catalog."""

    from app.modules.search.schemas import ENTITY_TYPES, parse_types

    assert parse_types(None) == set(ENTITY_TYPES)


def test_parse_types_csv_parses_multiple_values() -> None:
    """A comma-separated ``types`` string parses into the matching set."""

    from app.modules.search.schemas import parse_types

    assert parse_types("task,project") == {"task", "project"}


def test_parse_types_single_value_parses_to_singleton_set() -> None:
    """A single ``types`` value parses into a one-element set."""

    from app.modules.search.schemas import parse_types

    assert parse_types("comment") == {"comment"}


def test_parse_types_empty_string_raises_value_error() -> None:
    """An empty (or whitespace-only) ``types`` string is invalid."""

    from app.modules.search.schemas import parse_types

    with pytest.raises(ValueError):
        parse_types("   ")


def test_parse_types_unknown_value_raises_value_error() -> None:
    """A ``types`` token outside the catalog (task/project/comment) is invalid."""

    from app.modules.search.schemas import parse_types

    with pytest.raises(ValueError):
        parse_types("asset")


# ---------------------------------------------------------------------------
# T08 — RED: integration tests against GET /search (single-org happy path,
# ordering, meta, validation). `search/repository.py`, `service.py` and
# `router.py` don't exist yet — requests 404/error until T09-T11.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_returns_matches_across_all_entity_types(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A term present in a task, a project and a comment returns all three (R1)."""

    _, token = user
    project = await _create_project(client, token, "Proyecto Facturación")
    task = await _create_task(client, token, project["id"], "Revisar factura mensual")
    await _create_comment(client, token, task["id"], "Ya revisé la factura, todo bien.")

    response = await _search(client, token, q="factura")

    assert response.status_code == 200, response.text
    entity_types = {row["entity_type"] for row in response.json()["data"]}
    assert entity_types == {"task", "project", "comment"}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_types_filter_limits_result_to_requested_entities(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``types=task`` returns only ``entity_type=task`` rows (R1)."""

    _, token = user
    project = await _create_project(client, token, "Proyecto Facturación")
    await _create_task(client, token, project["id"], "Revisar factura mensual")

    response = await _search(client, token, q="factura", types="task")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data
    assert all(row["entity_type"] == "task" for row in data)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_task_result_includes_task_key(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A ``task`` result carries a ``task_key`` shaped like ``CODE-N`` (R1)."""

    _, token = user
    project = await _create_project(client, token, "Proyecto Facturación", methodology="kanban")
    await _create_task(client, token, project["id"], "Revisar factura mensual")

    response = await _search(client, token, q="factura", types="task")

    assert response.status_code == 200, response.text
    row = response.json()["data"][0]
    assert row["task_key"] is not None
    assert re.match(r"^[A-Z0-9]{2,10}-\d+$", row["task_key"])


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_comment_result_includes_task_id_and_snippet(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A ``comment`` result includes ``task_id`` context and a text snippet (R1)."""

    _, token = user
    project = await _create_project(client, token, "Proyecto Facturación")
    task = await _create_task(client, token, project["id"], "Tarea con adjuntos")
    comment = await _create_comment(
        client, token, task["id"], "La factura llegó ayer y está pendiente de pago."
    )

    response = await _search(client, token, q="factura", types="comment")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data) == 1
    row = data[0]
    assert row["entity_type"] == "comment"
    assert row["id"] == comment["id"]
    assert row["task_id"] == task["id"]
    assert "factura" in row["snippet"].lower()


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_orders_results_by_similarity_desc(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """An exact-word match ranks above a long sentence containing the same word."""

    _, token = user
    project = await _create_project(client, token, "Otro proyecto")
    exact = await _create_task(client, token, project["id"], "factura")
    long_task = await _create_task(
        client,
        token,
        project["id"],
        "Revisar la factura mensual de servicios variados del proveedor externo",
    )

    response = await _search(client, token, q="factura", types="task")

    assert response.status_code == 200, response.text
    ids = [row["id"] for row in response.json()["data"]]
    assert exact["id"] in ids and long_task["id"] in ids
    assert ids.index(exact["id"]) < ids.index(long_task["id"])


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_meta_always_includes_page_size_total(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``meta`` always carries ``page``/``size``/``total`` — even without params (design.md)."""

    _, token = user
    project = await _create_project(client, token, "Proyecto Facturación")
    await _create_task(client, token, project["id"], "Revisar factura mensual")

    response = await _search(client, token, q="factura")

    assert response.status_code == 200, response.text
    meta = response.json()["meta"]
    assert meta["page"] == 1
    assert meta["size"] == 20
    assert meta["total"] >= 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_query_shorter_than_two_chars_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A single-character ``q`` is rejected without running the search (R2)."""

    _, token = user

    response = await _search(client, token, q="a")

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "query_too_short"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_query_only_whitespace_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A whitespace-only ``q`` is rejected the same as an empty one (R2)."""

    _, token = user

    response = await client.get("/search", params={"q": "   "}, headers=_auth(token))

    assert response.status_code == 422, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_invalid_entity_type_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A ``types`` value outside the catalog is rejected (R3)."""

    _, token = user

    response = await _search(client, token, q="factura", types="asset")

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_search_type"


# ---------------------------------------------------------------------------
# T13 — RED: tenant isolation (per entity type), soft-delete exclusion and
# role-agnostic permissions (R4/R5/R6). `search/repository.py` does not
# filter by organization/`is_active` yet — these fail until T14.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_task_isolation_excludes_other_organization(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A task matching in org A never appears in org B's search (R4)."""

    project = await _create_project(client, two_orgs.a.token, "Proyecto A Facturación")
    await _create_task(
        client, two_orgs.a.token, project["id"], "Factura pendiente de pago"
    )

    response = await _search(client, two_orgs.b.token, q="factura", types="task")

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_project_isolation_excludes_other_organization(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A project matching in org A never appears in org B's search (R4)."""

    await _create_project(client, two_orgs.a.token, "Facturación Corporativa")

    response = await _search(client, two_orgs.b.token, q="facturación", types="project")

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_comment_isolation_excludes_other_organization(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A comment matching in org A never appears in org B's search (R4)."""

    project = await _create_project(client, two_orgs.a.token, "Proyecto A")
    task = await _create_task(
        client, two_orgs.a.token, project["id"], "Tarea con comentario"
    )
    await _create_comment(
        client, two_orgs.a.token, task["id"], "Factura confidencial de la organización A."
    )

    response = await _search(client, two_orgs.b.token, q="factura", types="comment")

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_excludes_soft_deleted_task(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A soft-deleted task is excluded from search results (R5)."""

    _, token = user
    project = await _create_project(client, token, "Proyecto Facturación")
    task = await _create_task(client, token, project["id"], "Factura a eliminar")

    delete_response = await client.delete(f"/tasks/{task['id']}", headers=_auth(token))
    assert delete_response.status_code == 204, delete_response.text

    response = await _search(client, token, q="factura", types="task")

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_excludes_soft_deleted_project(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """A soft-deleted project is excluded from search results (R5).

    No ``DELETE /projects/{id}`` endpoint exists yet, so the soft delete is
    applied directly through the ORM on the same ``session`` the ``client``
    fixture shares (visible to the request without crossing the SAVEPOINT).
    """

    from app.modules.projects.models import Project

    _, token = user
    project = await _create_project(client, token, "Proyecto Facturación Eliminado")

    project_row = await session.get(Project, uuid.UUID(project["id"]))
    assert project_row is not None
    project_row.is_active = False
    await session.flush()

    response = await _search(client, token, q="facturación", types="project")

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_excludes_soft_deleted_comment(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A soft-deleted comment is excluded from search results (R5)."""

    _, token = user
    project = await _create_project(client, token, "Proyecto Comentarios")
    task = await _create_task(client, token, project["id"], "Tarea con comentario")
    comment = await _create_comment(
        client, token, task["id"], "Factura adjunta al comentario."
    )

    delete_response = await client.delete(
        f"/comments/{comment['id']}", headers=_auth(token)
    )
    assert delete_response.status_code == 204, delete_response.text

    response = await _search(client, token, q="factura", types="comment")

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_search_viewer_role_can_search_without_restriction(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    make_member,
) -> None:
    """A ``viewer`` (the most restricted role) can still use /search (R6)."""

    from app.shared.enums import MemberRole

    _, viewer_token = await make_member(session, tenant, MemberRole.viewer)
    project = await _create_project(client, viewer_token, "Proyecto Facturación")
    await _create_task(client, viewer_token, project["id"], "Revisar factura mensual")

    response = await _search(client, viewer_token, q="factura")

    assert response.status_code == 200, response.text
    assert response.json()["data"]
