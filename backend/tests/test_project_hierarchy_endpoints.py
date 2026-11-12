"""Tests for the project-hierarchy HTTP surface (change 21-project-hierarchy,
tasks.md T2.12): ``PATCH /projects/{id}/parent``, ``GET /projects/{id}/tree``,
``GET /projects/{id}/progress``, plus ``parent_project_id`` on
``POST/GET /projects``.

R1-R7, R9-R11 (specs/project-hierarchy/spec.md, specs/projects/spec.md).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.shared.enums import MemberRole
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(
    client: AsyncClient,
    token: str,
    name: str,
    *,
    methodology: str = "planner",
    parent_project_id: str | None = None,
) -> dict:
    payload: dict = {"name": name, "methodology": methodology}
    if parent_project_id is not None:
        payload["parent_project_id"] = parent_project_id
    response = await client.post("/projects", json=payload, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_task(
    client: AsyncClient, token: str, project_id: str, title: str, status: str
) -> None:
    create = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": title},
        headers=_auth(token),
    )
    assert create.status_code == 201, create.text
    task_id = create.json()["data"]["id"]
    move = await client.patch(
        f"/tasks/{task_id}", json={"status": status}, headers=_auth(token)
    )
    assert move.status_code == 200, move.text


# ---------------------------------------------------------------------------
# R5 — Árbol jerárquico
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_tree_endpoint_reproduces_a_three_level_hierarchy(
    client: AsyncClient, tenant: Organization, user
) -> None:
    _, token = user
    root = await _create_project(client, token, "Seguridad de la Información")
    child = await _create_project(
        client, token, "Desarrollo", parent_project_id=root["id"]
    )
    grandchild = await _create_project(
        client, token, "Backend", parent_project_id=child["id"]
    )

    response = await client.get(
        f"/projects/{root['id']}/tree", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    tree = response.json()["data"]
    assert tree["id"] == root["id"]
    assert len(tree["children"]) == 1
    assert tree["children"][0]["id"] == child["id"]
    assert len(tree["children"][0]["children"]) == 1
    assert tree["children"][0]["children"][0]["id"] == grandchild["id"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_tree_endpoint_of_another_org_project_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    response = await client.get(
        f"/projects/{two_orgs.b.project.id}/tree",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# R6 — Avance consolidado (roll-up)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_progress_endpoint_reproduces_the_18_of_20_business_example(
    client: AsyncClient, tenant: Organization, user
) -> None:
    _, token = user
    umbrella = await _create_project(client, token, "Umbrella Progress")
    development = await _create_project(
        client, token, "Development Progress", parent_project_id=umbrella["id"]
    )
    security = await _create_project(
        client,
        token,
        "Security Progress",
        methodology="scrum",
        parent_project_id=umbrella["id"],
    )

    for i in range(8):
        await _create_task(client, token, development["id"], f"Dev done {i}", "Completada")
    for i in range(2):
        await _create_task(client, token, development["id"], f"Dev todo {i}", "Sin iniciar")
    for i in range(10):
        await _create_task(client, token, security["id"], f"Sec done {i}", "Done")

    response = await client.get(
        f"/projects/{umbrella['id']}/progress", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    progress = response.json()["data"]
    assert progress["rollup"]["done"] == 18
    assert progress["rollup"]["total"] == 20


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_progress_endpoint_excludes_cancelled_tasks_from_denominator(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user
) -> None:
    """``cancelled`` is not yet a reachable status via ``PATCH /tasks/{id}``
    (projects/spec.md, "Limitaciones y deuda conocida" — the state exists in
    the spec's exclusion rule but no methodology strategy exposes it as an
    allowed column today), so the 2 cancelled tasks are seeded directly
    through the ORM — same pattern as
    ``test_notification_deliveries_endpoint.py``'s ``_seed_notification``
    helper — while everything else in the test still goes through the real
    HTTP surface."""

    from app.modules.tasks.models import Task

    _, token = user
    project = await _create_project(client, token, "Cancelled Denominator")

    for i in range(5):
        await _create_task(client, token, project["id"], f"Done {i}", "Completada")
    for i in range(3):
        await _create_task(client, token, project["id"], f"Todo {i}", "Sin iniciar")
    for i in range(2):
        session.add(
            Task(
                project_id=project["id"],
                title=f"Cancelled {i}",
                status="cancelled",
            )
        )
    await session.flush()

    response = await client.get(
        f"/projects/{project['id']}/progress", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    progress = response.json()["data"]
    assert progress["self"]["done"] == 5
    assert progress["self"]["total"] == 8


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_progress_of_a_fresh_project_matches_the_dashboard_percent_done(
    client: AsyncClient, tenant: Organization, user
) -> None:
    """The roll-up ``percent_done`` of a standalone project's OWN counts must
    equal the dashboard's ``percent_done`` for that same project (design.md
    Decision 1, "el roll-up de un proyecto recién creado debe igualar su
    percent_done del dashboard")."""

    _, token = user
    project = await _create_project(client, token, "Dashboard Parity")

    for i in range(3):
        await _create_task(client, token, project["id"], f"Done {i}", "Completada")
    for i in range(2):
        await _create_task(client, token, project["id"], f"Todo {i}", "Sin iniciar")

    progress_response = await client.get(
        f"/projects/{project['id']}/progress", headers=_auth(token)
    )
    dashboard_response = await client.get("/dashboard/executive", headers=_auth(token))

    assert progress_response.status_code == 200, progress_response.text
    assert dashboard_response.status_code == 200, dashboard_response.text

    progress_percent = progress_response.json()["data"]["self"]["percent_done"]
    dashboard_rows = dashboard_response.json()["data"]["projects_progress"]
    dashboard_row = next(
        row for row in dashboard_rows if row["project"]["id"] == project["id"]
    )

    assert progress_percent == dashboard_row["percent_done"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_progress_endpoint_of_another_org_project_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    response = await client.get(
        f"/projects/{two_orgs.b.project.id}/progress",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# R4 — Reparentado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reparent_endpoint_moves_a_project_under_a_new_parent(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, make_member
) -> None:
    _, owner_token = user
    _, manager_token = await make_member(session, tenant, MemberRole.manager)
    development = await _create_project(client, owner_token, "Reparent Development")
    security = await _create_project(client, owner_token, "Reparent Security")

    response = await client.patch(
        f"/projects/{development['id']}/parent",
        json={"parent_project_id": security["id"]},
        headers=_auth(manager_token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"]["parent_project_id"] == security["id"]
    assert "message" in body


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reparent_endpoint_to_null_unlinks_the_project_to_root(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, make_member
) -> None:
    _, owner_token = user
    _, manager_token = await make_member(session, tenant, MemberRole.manager)
    root = await _create_project(client, owner_token, "Unlink Root")
    child = await _create_project(
        client, owner_token, "Unlink Child", parent_project_id=root["id"]
    )

    response = await client.patch(
        f"/projects/{child['id']}/parent",
        json={"parent_project_id": None},
        headers=_auth(manager_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["parent_project_id"] is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reparent_endpoint_rejects_a_cycle_and_leaves_hierarchy_intact(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, make_member
) -> None:
    _, owner_token = user
    _, manager_token = await make_member(session, tenant, MemberRole.manager)
    project_a = await _create_project(client, owner_token, "Cycle Endpoint A")
    project_b = await _create_project(
        client, owner_token, "Cycle Endpoint B", parent_project_id=project_a["id"]
    )

    response = await client.patch(
        f"/projects/{project_a['id']}/parent",
        json={"parent_project_id": project_b["id"]},
        headers=_auth(manager_token),
    )

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "project_cycle"

    # Hierarchy is untouched: B is still A's child, not the other way around.
    tree_response = await client.get(
        f"/projects/{project_a['id']}/tree", headers=_auth(owner_token)
    )
    tree = tree_response.json()["data"]
    assert tree["id"] == project_a["id"]
    assert tree["children"][0]["id"] == project_b["id"]


# ---------------------------------------------------------------------------
# R7 — Permisos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_cannot_reparent(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, make_member
) -> None:
    _, owner_token = user
    project = await _create_project(client, owner_token, "Permission Project")
    target = await _create_project(client, owner_token, "Permission Target")

    _, member_token = await make_member(session, tenant, MemberRole.member)

    response = await client.patch(
        f"/projects/{project['id']}/parent",
        json={"parent_project_id": target["id"]},
        headers=_auth(member_token),
    )

    assert response.status_code == 403


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_manager_can_reparent(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, make_member
) -> None:
    _, owner_token = user
    project = await _create_project(client, owner_token, "Manager Project")
    target = await _create_project(client, owner_token, "Manager Target")

    _, manager_token = await make_member(session, tenant, MemberRole.manager)

    response = await client.patch(
        f"/projects/{project['id']}/parent",
        json={"parent_project_id": target["id"]},
        headers=_auth(manager_token),
    )

    assert response.status_code == 200, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_can_read_tree_and_progress_without_restriction(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, make_member
) -> None:
    _, owner_token = user
    project = await _create_project(client, owner_token, "Member Read Project")

    _, member_token = await make_member(session, tenant, MemberRole.member)

    tree_response = await client.get(
        f"/projects/{project['id']}/tree", headers=_auth(member_token)
    )
    progress_response = await client.get(
        f"/projects/{project['id']}/progress", headers=_auth(member_token)
    )

    assert tree_response.status_code == 200
    assert progress_response.status_code == 200


# ---------------------------------------------------------------------------
# R10 — Creación con padre opcional / R11 — Exposición de parent_project_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_project_with_a_valid_parent_returns_201_with_parent_id(
    client: AsyncClient, tenant: Organization, user
) -> None:
    _, token = user
    parent = await _create_project(client, token, "Creation Parent")

    child = await _create_project(
        client, token, "Creation Child", parent_project_id=parent["id"]
    )

    assert child["parent_project_id"] == parent["id"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_project_without_parent_defaults_to_root(
    client: AsyncClient, tenant: Organization, user
) -> None:
    _, token = user
    project = await _create_project(client, token, "Rootless Creation")

    assert project["parent_project_id"] is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_project_with_invalid_parent_rejects_the_whole_creation(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """An invalid parent (another org) rejects creation atomically: no
    project is left behind (R10, todo-o-nada)."""

    response = await client.post(
        "/projects",
        json={
            "name": "Should Not Exist",
            "methodology": "planner",
            "parent_project_id": str(two_orgs.b.project.id),
        },
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404, response.text

    listing = await client.get("/projects", headers=_auth(two_orgs.a.token))
    names = {row["name"] for row in listing.json()["data"]}
    assert "Should Not Exist" not in names


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_projects_exposes_parent_project_id(
    client: AsyncClient, tenant: Organization, user
) -> None:
    _, token = user
    parent = await _create_project(client, token, "Listing Parent")
    child = await _create_project(
        client, token, "Listing Child", parent_project_id=parent["id"]
    )

    response = await client.get("/projects", headers=_auth(token))

    assert response.status_code == 200, response.text
    row = next(r for r in response.json()["data"] if r["id"] == child["id"])
    assert row["parent_project_id"] == parent["id"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_project_detail_of_a_root_exposes_null_parent(
    client: AsyncClient, tenant: Organization, user
) -> None:
    _, token = user
    project = await _create_project(client, token, "Detail Root")

    response = await client.get(f"/projects/{project['id']}", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert response.json()["data"]["parent_project_id"] is None
