"""Tests for the time_logs module (change 05, Batch A).

R1 Registro propio · R2 Edición/borrado del dueño (403 incl. manager/admin) ·
R3 Visibilidad propia vs. supervisión · R4 Listados paginados + rango de
fechas · R5 Agregación diaria y semanal (specs/time-logs/spec.md).

Uses the shared in-process fixtures (``client``/``tenant``/``user``).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/projects",
        json={"name": "Time Log Project", "methodology": "kanban"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_task(client: AsyncClient, token: str, project_id: str) -> str:
    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Implement feature"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_member(
    session: AsyncSession, tenant: Organization, role: str, *, suffix: str
) -> tuple[User, str]:
    """Create a second/third org member with an explicit role, plus a token."""

    from app.modules.organizations.models import OrganizationMember
    from app.shared.enums import MemberRole
    from app.shared.security import create_access_token, hash_password

    new_user = User(
        email=f"time-log-{suffix}@example.com",
        primer_nombre="Time",
        primer_apellido=suffix.capitalize(),
        hashed_password=hash_password("Test123*"),
    )
    session.add(new_user)
    await session.flush()
    session.add(
        OrganizationMember(
            organization_id=tenant.id,
            user_id=new_user.id,
            role=MemberRole(role),
        )
    )
    await session.flush()
    token = create_access_token(str(new_user.id))
    return new_user, token


# ---------------------------------------------------------------------------
# R1 — Registro propio de tiempo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_time_log_valid_returns_201_with_own_user_id(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A valid POST creates the entry with user_id = the authenticated caller."""

    owner, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)

    response = await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": "2026-02-10", "hours": 2.5, "note": "Avance inicial"},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["user_id"] == str(owner.id)
    assert body["task_id"] == task_id
    assert body["date"] == "2026-02-10"
    assert float(body["hours"]) == 2.5


@pytest.mark.parametrize("hours", [0, -1])
@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_time_log_rejects_non_positive_hours(
    hours: float, client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """hours <= 0 is rejected with 422 and no entry is created."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)

    response = await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": "2026-02-10", "hours": hours},
        headers=_auth(token),
    )

    assert response.status_code == 422

    listing = await client.get(f"/tasks/{task_id}/time-logs", headers=_auth(token))
    assert listing.json()["meta"]["total"] == 0


# ---------------------------------------------------------------------------
# R2 — Edición y borrado limitados al dueño
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_owner_can_edit_own_time_log(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """The owner can PATCH their own entry (200)."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)
    created = await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": "2026-02-10", "hours": 1},
        headers=_auth(token),
    )
    log_id = created.json()["data"]["id"]

    response = await client.patch(
        f"/time-logs/{log_id}", json={"hours": 3}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    assert float(response.json()["data"]["hours"]) == 3.0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_edit_by_other_member_forbidden(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user: tuple[User, str]
) -> None:
    """A different member (not the owner) gets 403 on PATCH; the entry is unchanged."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)
    created = await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": "2026-02-10", "hours": 1},
        headers=_auth(token),
    )
    log_id = created.json()["data"]["id"]

    _, other_token = await _create_member(session, tenant, "member", suffix="other")

    response = await client.patch(
        f"/time-logs/{log_id}", json={"hours": 9}, headers=_auth(other_token)
    )

    assert response.status_code == 403


@pytest.mark.parametrize("role", ["manager", "admin"])
@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_edit_and_delete_by_manager_or_admin_forbidden(
    role: str,
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Gate correction #2: manager/admin get 403 too — edit/delete is strictly owner-only."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)
    created = await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": "2026-02-10", "hours": 1},
        headers=_auth(token),
    )
    log_id = created.json()["data"]["id"]

    _, sup_token = await _create_member(session, tenant, role, suffix=f"sup-{role}")

    edit_response = await client.patch(
        f"/time-logs/{log_id}", json={"hours": 9}, headers=_auth(sup_token)
    )
    assert edit_response.status_code == 403

    delete_response = await client.delete(
        f"/time-logs/{log_id}", headers=_auth(sup_token)
    )
    assert delete_response.status_code == 403

    # The entry is unaffected: still listed under the task.
    listing = await client.get(f"/tasks/{task_id}/time-logs", headers=_auth(token))
    assert listing.json()["meta"]["total"] == 1


# ---------------------------------------------------------------------------
# R3 — Visibilidad propia vs. supervisión
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_cannot_list_other_users_time_logs(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user: tuple[User, str]
) -> None:
    """A ``member`` querying another user's time logs gets 403."""

    owner, owner_token = user
    project_id = await _create_project(client, owner_token)
    task_id = await _create_task(client, owner_token, project_id)
    await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": "2026-02-10", "hours": 1},
        headers=_auth(owner_token),
    )

    _, viewer_token = await _create_member(session, tenant, "member", suffix="viewer")

    response = await client.get(
        f"/users/{owner.id}/time-logs", headers=_auth(viewer_token)
    )

    assert response.status_code == 403


@pytest.mark.parametrize("role", ["manager", "admin"])
@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_manager_or_admin_can_list_other_users_time_logs(
    role: str,
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """A ``manager``/``admin`` querying another user's entries gets 200 with their data."""

    owner, owner_token = user
    project_id = await _create_project(client, owner_token)
    task_id = await _create_task(client, owner_token, project_id)
    await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": "2026-02-10", "hours": 4},
        headers=_auth(owner_token),
    )

    _, sup_token = await _create_member(session, tenant, role, suffix=f"list-{role}")

    response = await client.get(
        f"/users/{owner.id}/time-logs", headers=_auth(sup_token)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["user_id"] == str(owner.id)


# ---------------------------------------------------------------------------
# R4 — Listados paginados por tarea y por usuario + rango de fechas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_date_range_filter_on_user_time_logs(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``date_from``/``date_to`` restrict the user's listing to that window."""

    owner, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)

    await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": "2026-01-15", "hours": 2},
        headers=_auth(token),
    )
    await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": "2026-02-10", "hours": 3},
        headers=_auth(token),
    )

    response = await client.get(
        f"/users/{owner.id}/time-logs?date_from=2026-02-01&date_to=2026-02-28",
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["date"] == "2026-02-10"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_time_logs_listing_is_paginated(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``GET /tasks/{id}/time-logs`` returns ``meta {page, size, total}`` when paginated."""

    _, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)
    for day in ("2026-03-01", "2026-03-02", "2026-03-03"):
        await client.post(
            f"/tasks/{task_id}/time-logs",
            json={"date": day, "hours": 1},
            headers=_auth(token),
        )

    response = await client.get(
        f"/tasks/{task_id}/time-logs?page=1&size=2", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"] == {"page": 1, "size": 2, "total": 3}
    assert len(body["data"]) == 2


# ---------------------------------------------------------------------------
# R5 — Agregación diaria y semanal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_daily_summary_sums_two_entries_same_day(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Two entries the same day (different tasks) sum to a single daily total."""

    owner, token = user
    project_id = await _create_project(client, token)
    task_a = await _create_task(client, token, project_id)
    task_b = await _create_task(client, token, project_id)

    await client.post(
        f"/tasks/{task_a}/time-logs",
        json={"date": "2026-02-16", "hours": 3},
        headers=_auth(token),
    )
    await client.post(
        f"/tasks/{task_b}/time-logs",
        json={"date": "2026-02-16", "hours": 2},
        headers=_auth(token),
    )

    response = await client.get(
        f"/users/{owner.id}/time-logs/summary", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    daily = response.json()["data"]["daily"]
    entry = next(e for e in daily if e["date"] == "2026-02-16")
    assert float(entry["hours"]) == 5.0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_weekly_summary_sums_entries_within_iso_week(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Entries on different days of the same ISO week sum into one weekly total.

    2026-02-16 (Monday) and 2026-02-18 (Wednesday) fall in the same ISO week.
    """

    owner, token = user
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)

    await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": "2026-02-16", "hours": 4},
        headers=_auth(token),
    )
    await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": "2026-02-18", "hours": 6},
        headers=_auth(token),
    )

    response = await client.get(
        f"/users/{owner.id}/time-logs/summary", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    weekly = response.json()["data"]["weekly"]
    matching = [w for w in weekly if w["week_start"] == "2026-02-16"]
    assert len(matching) == 1
    assert float(matching[0]["hours"]) == 10.0
