"""Tests for the executive dashboard (/dashboard/executive, /dashboard/performance).

R1 ``by_assignee`` agrupa tareas en curso por persona · R2 ``at_risk``
incluye ``risk_flag``/próximas a vencer · R3 ``workload``+
``projects_progress``+totales · R4 ``GET /dashboard/performance`` con
``sprint_id`` opcional (openspec/specs/dashboard-executive/spec.md).

Matriz de permisos: los 4 ``MemberRole`` reciben 2xx (sin gate de rol).
``work_gap`` YA cubierto por ``test_dashboard_work_gap.py`` (cambio 05) —
no se duplica aquí.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.shared.enums import MemberRole
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: AsyncClient, token: str, methodology: str = "kanban") -> str:
    response = await client.post(
        "/projects",
        json={"name": "Dashboard Project", "methodology": methodology},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_task(
    client: AsyncClient, token: str, project_id: str, *, assignee_id: str, **extra
) -> str:
    payload = {"title": "Dashboard task", "assignee_id": assignee_id, **extra}
    response = await client.post(
        f"/projects/{project_id}/tasks", json=payload, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


# ---------------------------------------------------------------------------
# R1 — by_assignee agrupa tareas en curso por persona
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_by_assignee_groups_in_progress_tasks_per_person(
    client: AsyncClient, tenant: Organization, user
) -> None:
    """A task moved to an in-between column ("Doing", neither first nor
    last) shows up under its assignee in ``by_assignee``.
    """

    owner, token = user
    project_id = await _create_project(client, token, "kanban")
    task_id = await _create_task(client, token, project_id, assignee_id=str(owner.id))
    await client.patch(
        f"/tasks/{task_id}", json={"status": "Doing"}, headers=_auth(token)
    )

    response = await client.get("/dashboard/executive", headers=_auth(token))

    assert response.status_code == 200, response.text
    by_assignee = response.json()["data"]["by_assignee"]
    entry = next(row for row in by_assignee if row["user"]["id"] == str(owner.id))
    assert entry["active_count"] == 1
    assert any(t["id"] == task_id for t in entry["in_progress"])


# ---------------------------------------------------------------------------
# R2 — at_risk incluye risk_flag y tareas próximas a vencer sin completar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_at_risk_includes_flagged_and_overdue_tasks(
    client: AsyncClient, tenant: Organization, user
) -> None:
    """Both an explicitly ``risk_flag``-ged task and an overdue,
    not-yet-done task appear in ``at_risk``.
    """

    owner, token = user
    project_id = await _create_project(client, token, "kanban")

    flagged_task_id = await _create_task(
        client, token, project_id, assignee_id=str(owner.id)
    )
    await client.patch(
        f"/tasks/{flagged_task_id}", json={"risk_flag": True}, headers=_auth(token)
    )

    overdue_due_date = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    overdue_task_id = await _create_task(
        client,
        token,
        project_id,
        assignee_id=str(owner.id),
        due_date=overdue_due_date,
    )

    response = await client.get("/dashboard/executive", headers=_auth(token))

    assert response.status_code == 200, response.text
    at_risk_ids = {row["id"] for row in response.json()["data"]["at_risk"]}
    assert flagged_task_id in at_risk_ids
    assert overdue_task_id in at_risk_ids


# ---------------------------------------------------------------------------
# R3 — workload + projects_progress + totales
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_workload_projects_progress_and_totals(
    client: AsyncClient, tenant: Organization, user
) -> None:
    """``workload`` reports the active task count per member,
    ``projects_progress`` the per-project done ratio, ``totals`` the
    organization-wide counters.
    """

    owner, token = user
    project_id = await _create_project(client, token, "kanban")
    done_task_id = await _create_task(
        client, token, project_id, assignee_id=str(owner.id)
    )
    await client.patch(
        f"/tasks/{done_task_id}", json={"status": "Done"}, headers=_auth(token)
    )
    await _create_task(client, token, project_id, assignee_id=str(owner.id))

    response = await client.get("/dashboard/executive", headers=_auth(token))

    assert response.status_code == 200, response.text
    body = response.json()["data"]

    workload_entry = next(
        row for row in body["workload"] if row["user"]["id"] == str(owner.id)
    )
    assert workload_entry["active_count"] == 1  # only the non-done task

    progress_entry = next(
        row for row in body["projects_progress"] if row["project"]["id"] == project_id
    )
    assert progress_entry["total"] == 2
    assert progress_entry["done"] == 1
    assert progress_entry["percent_done"] == 50

    totals = body["totals"]
    assert totals["projects"] == 1
    assert totals["tasks"] == 2


# ---------------------------------------------------------------------------
# R4 — GET /dashboard/performance con sprint_id opcional
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_performance_reports_completed_tasks_and_supports_sprint_filter(
    client: AsyncClient, tenant: Organization, user
) -> None:
    """A completed task raises the collaborator's ``completed_tasks``, and
    passing ``sprint_id`` restricts the figures to that sprint only.
    """

    owner, token = user
    project_id = await _create_project(client, token, "scrum")
    sprint = await client.post(
        f"/projects/{project_id}/sprints",
        json={"name": "Perf Sprint"},
        headers=_auth(token),
    )
    sprint_id = sprint.json()["data"]["id"]

    task_id = await _create_task(
        client, token, project_id, assignee_id=str(owner.id), sprint_id=sprint_id
    )
    await client.patch(
        f"/tasks/{task_id}", json={"status": "Done"}, headers=_auth(token)
    )

    unfiltered = await client.get("/dashboard/performance", headers=_auth(token))
    assert unfiltered.status_code == 200, unfiltered.text
    unfiltered_entry = next(
        row
        for row in unfiltered.json()["data"]["collaborators"]
        if row["user"]["id"] == str(owner.id)
    )
    assert unfiltered_entry["completed_tasks"] == 1

    filtered = await client.get(
        "/dashboard/performance",
        params={"sprint_id": sprint_id},
        headers=_auth(token),
    )
    assert filtered.status_code == 200, filtered.text
    filtered_entry = next(
        row
        for row in filtered.json()["data"]["collaborators"]
        if row["user"]["id"] == str(owner.id)
    )
    assert filtered_entry["completed_tasks"] == 1


# ---------------------------------------------------------------------------
# Matriz de permisos — sin gate de rol
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role", [MemberRole.admin, MemberRole.manager, MemberRole.member, MemberRole.viewer]
)
@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_executive_dashboard_has_no_role_gate(
    role: MemberRole,
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    make_member,
) -> None:
    """Every ``MemberRole`` — including ``viewer`` — gets 2xx from the
    dashboard: only authentication + membership, no role gate.
    """

    _, token = await make_member(session, tenant, role)

    response = await client.get("/dashboard/executive", headers=_auth(token))

    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Aislamiento entre organizaciones (two_orgs)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dashboard_never_surfaces_another_organizations_project(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """org A's executive dashboard never includes org B's project in
    ``projects_progress``.
    """

    response = await client.get(
        "/dashboard/executive", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 200, response.text
    project_ids = {
        row["project"]["id"] for row in response.json()["data"]["projects_progress"]
    }
    assert str(two_orgs.a.project.id) in project_ids
    assert str(two_orgs.b.project.id) not in project_ids
