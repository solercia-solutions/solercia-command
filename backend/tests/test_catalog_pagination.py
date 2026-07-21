"""Pagination tests for ``GET /admin/dependencies``, ``GET /projects`` and
``GET /projects/{project_id}/sprints`` (R1, R2, R3).

Sort/order scenarios avoid ``created_at`` and instead use ``name``: Postgres
``now()`` is transaction-scoped, so every write inside the shared SAVEPOINT
session gets the SAME ``created_at`` (see test_tasks_pagination.py).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.dependencies.models import Dependency
from app.modules.organizations.models import Organization
from app.modules.roles.models import Role, UserRole
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _grant_admin(session: AsyncSession, tenant: Organization, user: User) -> None:
    role = Role(organization_id=tenant.id, code="ADMIN", name="Administrator")
    session.add(role)
    await session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.flush()


async def _seed_dependencies(
    session: AsyncSession, tenant: Organization, names: list[str]
) -> None:
    for name in names:
        session.add(Dependency(organization_id=tenant.id, name=name))
    await session.flush()


async def _create_project(
    client: AsyncClient, token: str, name: str, methodology: str = "kanban"
) -> str:
    response = await client.post(
        "/projects",
        json={"name": name, "methodology": methodology},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_sprints(
    client: AsyncClient, token: str, project_id: str, names: list[str]
) -> None:
    for name in names:
        response = await client.post(
            f"/projects/{project_id}/sprints",
            json={"name": name},
            headers=_auth(token),
        )
        assert response.status_code == 201, response.text


# ---------------------------------------------------------------------------
# GET /admin/dependencies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_dependencies_without_params_is_byte_compatible(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    caller, token = user
    await _grant_admin(session, tenant, caller)
    await _seed_dependencies(session, tenant, ["Alpha", "Beta", "Gamma"])

    response = await client.get("/admin/dependencies", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 3
    assert body["meta"] == {"total": 3}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_dependencies_page_and_size_returns_correct_slice(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    caller, token = user
    await _grant_admin(session, tenant, caller)
    await _seed_dependencies(session, tenant, ["Alpha", "Beta", "Gamma", "Delta", "Echo"])

    response = await client.get(
        "/admin/dependencies",
        params={"page": 2, "size": 2, "sort": "name", "order": "asc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 2, "size": 2, "total": 5}
    # Alphabetical asc: Alpha, Beta, Delta, Echo, Gamma → page2/size2 = Delta, Echo
    assert [d["name"] for d in body["data"]] == ["Delta", "Echo"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_dependencies_sort_outside_whitelist_is_422(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    caller, token = user
    await _grant_admin(session, tenant, caller)

    response = await client.get(
        "/admin/dependencies", params={"sort": "organization_id"}, headers=_auth(token)
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_sort_field"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_dependencies_sort_name_desc_orders_results(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    caller, token = user
    await _grant_admin(session, tenant, caller)
    await _seed_dependencies(session, tenant, ["Alpha", "Beta", "Gamma"])

    response = await client.get(
        "/admin/dependencies",
        params={"sort": "name", "order": "desc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert [d["name"] for d in response.json()["data"]] == ["Gamma", "Beta", "Alpha"]


# ---------------------------------------------------------------------------
# GET /projects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_projects_without_params_is_byte_compatible(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    await _create_project(client, token, "Project Alpha")
    await _create_project(client, token, "Project Beta")

    response = await client.get("/projects", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"total": 2}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_projects_page_and_size_returns_correct_slice(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    for name in ["P Alpha", "P Beta", "P Gamma", "P Delta", "P Echo"]:
        await _create_project(client, token, name)

    response = await client.get(
        "/projects",
        params={"page": 2, "size": 2, "sort": "name", "order": "asc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 2, "size": 2, "total": 5}
    # Alphabetical asc: P Alpha, P Beta, P Delta, P Echo, P Gamma
    assert [p["name"] for p in body["data"]] == ["P Delta", "P Echo"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_projects_sort_outside_whitelist_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user

    response = await client.get(
        "/projects", params={"sort": "task_counter"}, headers=_auth(token)
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_sort_field"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_projects_sort_name_desc_orders_results(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    await _create_project(client, token, "P Alpha")
    await _create_project(client, token, "P Beta")

    response = await client.get(
        "/projects",
        params={"sort": "name", "order": "desc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert [p["name"] for p in response.json()["data"]] == ["P Beta", "P Alpha"]


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/sprints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_sprints_without_params_is_byte_compatible(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    project_id = await _create_project(client, token, "Scrum Project", "scrum")
    await _create_sprints(client, token, project_id, ["Sprint 1", "Sprint 2"])

    response = await client.get(
        f"/projects/{project_id}/sprints", headers=_auth(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    # change 30-backlog-sprints-agrupados: the envelope intentionally grows
    # a `backlog` aggregate (never null) — the rest of the shape is still
    # byte-compatible (no `page`/`size` when pagination isn't requested).
    assert body["meta"] == {
        "total": 2,
        "backlog": {"story_count": 0, "estimation_hours_sum": 0},
    }


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_sprints_page_and_size_returns_correct_slice(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    project_id = await _create_project(client, token, "Scrum Project", "scrum")
    await _create_sprints(
        client,
        token,
        project_id,
        ["Sprint A", "Sprint B", "Sprint C", "Sprint D", "Sprint E"],
    )

    response = await client.get(
        f"/projects/{project_id}/sprints",
        params={"page": 2, "size": 2, "sort": "name", "order": "asc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    # change 30-backlog-sprints-agrupados: `backlog` aggregate is present
    # regardless of pagination.
    assert body["meta"] == {
        "page": 2,
        "size": 2,
        "total": 5,
        "backlog": {"story_count": 0, "estimation_hours_sum": 0},
    }
    assert [s["name"] for s in body["data"]] == ["Sprint C", "Sprint D"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_sprints_sort_outside_whitelist_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    project_id = await _create_project(client, token, "Scrum Project", "scrum")

    response = await client.get(
        f"/projects/{project_id}/sprints",
        params={"sort": "goal"},
        headers=_auth(token),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_sort_field"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_sprints_sort_name_desc_orders_results(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    project_id = await _create_project(client, token, "Scrum Project", "scrum")
    await _create_sprints(client, token, project_id, ["Sprint A", "Sprint B"])

    response = await client.get(
        f"/projects/{project_id}/sprints",
        params={"sort": "name", "order": "desc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert [s["name"] for s in response.json()["data"]] == ["Sprint B", "Sprint A"]
