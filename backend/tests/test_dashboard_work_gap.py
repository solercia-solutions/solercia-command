"""Tests for the dashboard executive ``work_gap`` block (change 05, Batch C).

R11 Cruce horas/tareas · R12 Colaboradores sin actividad reciente
(specs/dashboard-executive/spec.md). ``work_gap`` lives INSIDE
``GET /dashboard/executive`` (design.md, "Correcciones de gate (2026-07-11)"
#1) — there is no separate ``/dashboard/discrepancy`` endpoint.

Uses the shared in-process fixtures (``client``/``tenant``/``user``).
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _iso_days_ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).date().isoformat()


async def _create_project(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/projects",
        json={"name": "Work Gap Project", "methodology": "kanban"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_task(
    client: AsyncClient,
    token: str,
    project_id: str,
    *,
    assignee_id: str,
    estimation_hours: float | None = None,
) -> str:
    payload: dict = {"title": "Work item", "assignee_id": assignee_id}
    if estimation_hours is not None:
        payload["estimation_hours"] = estimation_hours
    response = await client.post(
        f"/projects/{project_id}/tasks", json=payload, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _log_time(
    client: AsyncClient, token: str, task_id: str, *, date: str, hours: float
) -> None:
    response = await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": date, "hours": hours},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text


async def _create_member(
    session: AsyncSession, tenant: Organization, *, suffix: str
) -> tuple[User, str]:
    from app.modules.organizations.models import OrganizationMember
    from app.shared.enums import MemberRole
    from app.shared.security import create_access_token, hash_password

    new_user = User(
        email=f"work-gap-{suffix}@example.com",
        primer_nombre="Gap",
        primer_apellido=suffix.capitalize(),
        hashed_password=hash_password("Test123*"),
    )
    session.add(new_user)
    await session.flush()
    session.add(
        OrganizationMember(
            organization_id=tenant.id, user_id=new_user.id, role=MemberRole.member
        )
    )
    await session.flush()
    token = create_access_token(str(new_user.id))
    return new_user, token


def _entry_for(work_gap: dict, user_id: str) -> dict:
    return next(row for row in work_gap["by_user"] if row["user"]["id"] == user_id)


# ---------------------------------------------------------------------------
# R11 — Cruce asignado vs. realizado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_work_gap_reports_hours_logged_vs_estimated(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """10 estimated hours vs. 6 logged hours are both reported for the collaborator."""

    owner, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(
        client, token, project_id, assignee_id=str(owner.id), estimation_hours=10
    )
    await _log_time(client, token, task_id, date=_iso_days_ago(0), hours=6)

    response = await client.get("/dashboard/executive", headers=_auth(token))
    assert response.status_code == 200, response.text
    work_gap = response.json()["data"]["work_gap"]
    entry = _entry_for(work_gap, str(owner.id))

    assert float(entry["hours_logged"]) == 6.0
    assert float(entry["hours_estimated"]) == 10.0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_work_gap_reports_tasks_assigned_vs_with_activity(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """5 assigned active tasks, 3 with a recent time-log, report 5 vs. 3."""

    owner, token = user
    project_id = await _create_project(client, token)

    task_ids = [
        await _create_task(client, token, project_id, assignee_id=str(owner.id))
        for _ in range(5)
    ]
    for task_id in task_ids[:3]:
        await _log_time(client, token, task_id, date=_iso_days_ago(0), hours=1)

    response = await client.get("/dashboard/executive", headers=_auth(token))
    assert response.status_code == 200, response.text
    work_gap = response.json()["data"]["work_gap"]
    entry = _entry_for(work_gap, str(owner.id))

    assert entry["tasks_assigned"] == 5
    assert entry["tasks_with_activity"] == 3


# ---------------------------------------------------------------------------
# R12 — Colaboradores sin actividad reciente
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_collaborator_with_zero_activity_flagged_by_default(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """An active assignee with no time-log and no history ever is flagged (default N=3)."""

    owner, token = user
    project_id = await _create_project(client, token)
    await _create_task(client, token, project_id, assignee_id=str(owner.id))

    response = await client.get("/dashboard/executive", headers=_auth(token))
    assert response.status_code == 200, response.text
    work_gap = response.json()["data"]["work_gap"]
    flagged_ids = {row["id"] for row in work_gap["no_recent_activity"]}

    assert str(owner.id) in flagged_ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_threshold_days_configurable(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user: tuple[User, str]
) -> None:
    """Last activity 4 days ago: flagged at the default threshold, not at threshold_days=5."""

    _, owner_token = user
    collaborator, collaborator_token = await _create_member(session, tenant, suffix="four-days")
    project_id = await _create_project(client, owner_token)
    task_id = await _create_task(
        client, owner_token, project_id, assignee_id=str(collaborator.id)
    )
    await _log_time(client, collaborator_token, task_id, date=_iso_days_ago(4), hours=1)

    default_response = await client.get("/dashboard/executive", headers=_auth(owner_token))
    default_flagged = {
        row["id"] for row in default_response.json()["data"]["work_gap"]["no_recent_activity"]
    }
    assert str(collaborator.id) in default_flagged

    wider_response = await client.get(
        "/dashboard/executive?threshold_days=5", headers=_auth(owner_token)
    )
    wider_flagged = {
        row["id"] for row in wider_response.json()["data"]["work_gap"]["no_recent_activity"]
    }
    assert str(collaborator.id) not in wider_flagged


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_collaborator_with_recent_activity_not_flagged(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user: tuple[User, str]
) -> None:
    """A time-log logged yesterday keeps the collaborator out of the list (default N=3)."""

    _, owner_token = user
    collaborator, collaborator_token = await _create_member(session, tenant, suffix="yesterday")
    project_id = await _create_project(client, owner_token)
    task_id = await _create_task(
        client, owner_token, project_id, assignee_id=str(collaborator.id)
    )
    await _log_time(client, collaborator_token, task_id, date=_iso_days_ago(1), hours=2)

    response = await client.get("/dashboard/executive", headers=_auth(owner_token))
    flagged_ids = {row["id"] for row in response.json()["data"]["work_gap"]["no_recent_activity"]}

    assert str(collaborator.id) not in flagged_ids


# ---------------------------------------------------------------------------
# T23 — performance stays unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_performance_endpoint_contract_unchanged(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``GET /dashboard/performance`` keeps its existing shape (no work_gap here)."""

    _, token = user
    response = await client.get("/dashboard/performance", headers=_auth(token))

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert "collaborators" in body
    assert "generated_at" in body
    assert "work_gap" not in body
