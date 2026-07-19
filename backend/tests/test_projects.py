"""Tests for projects (/projects).

R1 creación con metodología válida (comportamiento leído desde la strategy)
· R3 ``GET /{id}/velocity`` (puntos por sprint cerrado + promedio +
proyección) · R4 aislamiento entre organizaciones
(openspec/specs/projects/spec.md).

DEVIATION from tasks.md T22: the as-built API has NO ``PATCH``/``DELETE
/projects/{id}`` route (projects/spec.md, "Limitaciones y deuda conocida" —
"NO hay PATCH ni DELETE de proyectos vía API"). Only the documented
isolation surface (``GET /projects`` listing + ``GET /projects/{id}``) is
tested for R4; adding PATCH/DELETE assertions here would test routes that
do not exist.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# R1 — Creación con metodología: comportamiento leído desde la strategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_project_with_scrum_returns_201_with_scrum_columns(
    client: AsyncClient, tenant, user
) -> None:
    """A scrum project is created (201) and its ``methodology_info`` reflects
    the scrum strategy's contract, not a hardcoded default.
    """

    _, token = user

    response = await client.post(
        "/projects",
        json={"name": "Scrum Project", "methodology": "scrum"},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["methodology"] == "scrum"
    info = body["methodology_info"]
    assert info["sprints_enabled"] is True
    assert info["allowed_statuses"] == ["To Do", "In Progress", "In Review", "Done"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_status_validated_against_scrum_strategy(
    client: AsyncClient, tenant, user
) -> None:
    """A task in a scrum project cannot move to a status outside the
    strategy's ``allowed_statuses()`` — the project's methodology drives it,
    never a hardcoded status set.
    """

    _, token = user
    project = await client.post(
        "/projects",
        json={"name": "Scrum Validation Project", "methodology": "scrum"},
        headers=_auth(token),
    )
    project_id = project.json()["data"]["id"]
    task = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Scrum task"},
        headers=_auth(token),
    )
    task_id = task.json()["data"]["id"]

    response = await client.patch(
        f"/tasks/{task_id}", json={"status": "not-a-real-status"}, headers=_auth(token)
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# R3 — GET /{id}/velocity: puntos por sprint cerrado + promedio + proyección
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_velocity_reports_closed_sprint_points_average_and_projection(
    client: AsyncClient, tenant, user
) -> None:
    """After closing a sprint with completed points, ``/velocity`` reports the
    per-sprint series, the average and a backlog-based projection.
    """

    _, token = user
    project = await client.post(
        "/projects",
        json={"name": "Velocity Project", "methodology": "scrum"},
        headers=_auth(token),
    )
    project_id = project.json()["data"]["id"]

    sprint = await client.post(
        f"/projects/{project_id}/sprints",
        json={"name": "Sprint 1"},
        headers=_auth(token),
    )
    sprint_id = sprint.json()["data"]["id"]

    task = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Done task", "sprint_id": sprint_id, "estimation_points": 5},
        headers=_auth(token),
    )
    task_id = task.json()["data"]["id"]
    await client.patch(
        f"/tasks/{task_id}", json={"status": "Done"}, headers=_auth(token)
    )

    close = await client.post(
        f"/sprints/{sprint_id}/close", headers=_auth(token)
    )
    assert close.status_code == 200, close.text

    response = await client.get(
        f"/projects/{project_id}/velocity", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert len(body["series"]) == 1
    assert body["series"][0]["completed_points"] == 5
    assert body["average_velocity"] == 5.0
    assert body["projected_sprints"] is not None


# ---------------------------------------------------------------------------
# R4 — Aislamiento entre organizaciones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_projects_listing_never_crosses_organizations(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """``GET /projects`` for org A never includes org B's project."""

    response = await client.get("/projects", headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert str(two_orgs.a.project.id) in ids
    assert str(two_orgs.b.project.id) not in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_project_of_other_org_by_id_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A direct ``GET /projects/{id}`` for another org's project never
    succeeds — 404, never 200 with foreign data.
    """

    response = await client.get(
        f"/projects/{two_orgs.b.project.id}", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# projects delta R1 — lead_user_id (change 23-org-role-templates)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_project_without_template_keeps_lead_user_id_null(
    client: AsyncClient, tenant, user
) -> None:
    """A project created via the plain ``POST /projects`` flow (no template
    instantiation involved) keeps ``lead_user_id = null`` — compatibility
    scenario of the ``projects`` delta spec."""

    _, token = user

    response = await client.post(
        "/projects",
        json={"name": "Sin Plantilla", "methodology": "planner"},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["lead_user_id"] is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_projects_listing_exposes_lead_user_id_per_element(
    client: AsyncClient, tenant, user
) -> None:
    """``GET /projects`` exposes ``lead_user_id`` on every listed element."""

    _, token = user

    created = await client.post(
        "/projects",
        json={"name": "Listado Con Responsable", "methodology": "planner"},
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text

    response = await client.get("/projects", headers=_auth(token))

    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert rows
    assert all("lead_user_id" in row for row in rows)


# ---------------------------------------------------------------------------
# No-regresión — extracción de _create_project_unit() (Lote 2, tasks.md T2.1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_project_persists_in_a_single_call_no_regression(
    client: AsyncClient, tenant, user
) -> None:
    """No-regresión: tras extraer ``_create_project_unit()`` sin commit,
    ``POST /projects`` sigue devolviendo 201 y dejando el proyecto persistido
    en UNA sola llamada — ``create_project`` público sigue siendo
    ``_create_project_unit() + repo.save()`` (design.md Decisión 3)."""

    _, token = user

    response = await client.post(
        "/projects",
        json={"name": "Persistencia Atómica", "methodology": "kanban"},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    project_id = response.json()["data"]["id"]

    fetched = await client.get(f"/projects/{project_id}", headers=_auth(token))
    assert fetched.status_code == 200
    assert fetched.json()["data"]["name"] == "Persistencia Atómica"
