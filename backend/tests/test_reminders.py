"""Tests for the reminders module (change 06, Fase A — CRUD).

R1 Creación manual · R2 Listado/consulta solo-dueño · R3 Edición/cancelación en
scheduled · R4 Aislamiento multi-tenant/personal (ni admin ve lo ajeno) ·
R5 Configuración de ReminderRule (specs/reminders/spec.md).

Fase B (T13) extends this file with the admin-only ``POST /reminders/dispatch``
tests. Uses the shared in-process fixtures (client/tenant/user/two_orgs/
make_member).
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from app.shared.enums import MemberRole
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _future_iso(days: int = 1) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def _past_iso(days: int = 1) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# R1 — Creación de recordatorio manual
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_reminder_valid_returns_scheduled(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A valid POST creates the reminder with status=scheduled and created_by=caller."""

    owner, token = user
    response = await client.post(
        "/reminders",
        json={"remind_at": _future_iso(), "message": "Llamar al proveedor"},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["status"] == "scheduled"
    assert body["created_by"] == str(owner.id)
    assert body["updated_by"] == str(owner.id)
    assert body["message"] == "Llamar al proveedor"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_reminder_past_remind_at_rejected(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """remind_at in the past is rejected with 422 and no record is created."""

    _, token = user
    response = await client.post(
        "/reminders",
        json={"remind_at": _past_iso(), "message": "Recordatorio vencido"},
        headers=_auth(token),
    )

    assert response.status_code == 422

    listing = await client.get("/reminders", headers=_auth(token))
    assert listing.json()["meta"]["total"] == 0


# ---------------------------------------------------------------------------
# R2 — Listado y consulta exclusivos del dueño
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_reminders_paginated_and_filtered_by_status(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
    make_member,
) -> None:
    """A user with 5 reminders + another user with 2 only sees their own, filtered by status."""

    _, token = user
    _, other_token = await make_member(session, tenant, MemberRole.member)

    for i in range(5):
        response = await client.post(
            "/reminders",
            json={"remind_at": _future_iso(days=i + 1), "message": f"R{i}"},
            headers=_auth(token),
        )
        assert response.status_code == 201, response.text

    for i in range(2):
        response = await client.post(
            "/reminders",
            json={"remind_at": _future_iso(days=i + 1), "message": f"Other{i}"},
            headers=_auth(other_token),
        )
        assert response.status_code == 201, response.text

    listing = await client.get(
        "/reminders",
        params={"status": "scheduled", "page": 1, "size": 10},
        headers=_auth(token),
    )
    assert listing.status_code == 200
    body = listing.json()
    assert body["meta"]["total"] == 5
    assert len(body["data"]) == 5
    assert all(r["status"] == "scheduled" for r in body["data"])


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_other_users_reminder_returns_404(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
    make_member,
) -> None:
    """Fetching another user's reminder by id returns 404, not 403."""

    _, owner_token = user
    _, other_token = await make_member(session, tenant, MemberRole.member)

    create = await client.post(
        "/reminders",
        json={"remind_at": _future_iso(), "message": "Privado"},
        headers=_auth(other_token),
    )
    assert create.status_code == 201, create.text
    reminder_id = create.json()["data"]["id"]

    response = await client.get(f"/reminders/{reminder_id}", headers=_auth(owner_token))
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# R3 — Edición y cancelación solo en scheduled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_owner_can_edit_scheduled_reminder(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """PATCH with a new future remind_at updates the reminder and updated_by."""

    owner, token = user
    create = await client.post(
        "/reminders",
        json={"remind_at": _future_iso(days=1), "message": "Original"},
        headers=_auth(token),
    )
    assert create.status_code == 201, create.text
    reminder_id = create.json()["data"]["id"]

    response = await client.patch(
        f"/reminders/{reminder_id}",
        json={"remind_at": _future_iso(days=5), "message": "Actualizado"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["message"] == "Actualizado"
    assert body["updated_by"] == str(owner.id)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_edit_fired_reminder_rejected(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """PATCHing a reminder already in status=fired responds 422."""

    from app.modules.reminders.models import Reminder
    from app.shared.enums import ReminderStatus

    _, token = user
    create = await client.post(
        "/reminders",
        json={"remind_at": _future_iso(), "message": "Se disparará"},
        headers=_auth(token),
    )
    assert create.status_code == 201, create.text
    reminder_id = create.json()["data"]["id"]

    result = await session.execute(select(Reminder).where(Reminder.id == reminder_id))
    reminder = result.scalar_one()
    reminder.status = ReminderStatus.fired
    session.add(reminder)
    await session.flush()

    response = await client.patch(
        f"/reminders/{reminder_id}",
        json={"message": "Intento tardío"},
        headers=_auth(token),
    )
    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_scheduled_reminder_cancels_it(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """DELETE cancels (status=cancelled) a scheduled reminder."""

    _, token = user
    create = await client.post(
        "/reminders",
        json={"remind_at": _future_iso(), "message": "A cancelar"},
        headers=_auth(token),
    )
    assert create.status_code == 201, create.text
    reminder_id = create.json()["data"]["id"]

    response = await client.delete(f"/reminders/{reminder_id}", headers=_auth(token))
    assert response.status_code == 204

    listing = await client.get(
        "/reminders", params={"status": "cancelled"}, headers=_auth(token)
    )
    ids = [r["id"] for r in listing.json()["data"]]
    assert reminder_id in ids


# ---------------------------------------------------------------------------
# R4 — Aislamiento multi-tenant y personal (ni admin ve lo ajeno)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_cross_org_reminder_access_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """A member of org B cannot GET/PATCH/DELETE a reminder that belongs to org A."""

    create = await client.post(
        "/reminders",
        json={"remind_at": _future_iso(), "message": "Org A only"},
        headers=_auth(two_orgs.a.token),
    )
    assert create.status_code == 201, create.text
    reminder_id = create.json()["data"]["id"]

    get_response = await client.get(
        f"/reminders/{reminder_id}", headers=_auth(two_orgs.b.token)
    )
    assert get_response.status_code == 404

    patch_response = await client.patch(
        f"/reminders/{reminder_id}",
        json={"message": "Hijack"},
        headers=_auth(two_orgs.b.token),
    )
    assert patch_response.status_code == 404

    delete_response = await client.delete(
        f"/reminders/{reminder_id}", headers=_auth(two_orgs.b.token)
    )
    assert delete_response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_admin_does_not_see_other_users_reminders(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
    make_member,
) -> None:
    """An admin in the same org as U1 does not receive U1's reminders on GET /reminders."""

    _, owner_token = user
    _, admin_token = await make_member(session, tenant, MemberRole.admin)

    create = await client.post(
        "/reminders",
        json={"remind_at": _future_iso(), "message": "De U1"},
        headers=_auth(owner_token),
    )
    assert create.status_code == 201, create.text

    listing = await client.get("/reminders", headers=_auth(admin_token))
    assert listing.json()["meta"]["total"] == 0


# ---------------------------------------------------------------------------
# R5 — Configuración de ReminderRule por usuario
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_reminder_rule_task_due_soon(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Creating a task_due_soon rule with lead_days=3 defaults to enabled=true."""

    _, token = user
    response = await client.post(
        "/reminder-rules",
        json={"rule_type": "task_due_soon", "lead_days": 3},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["rule_type"] == "task_due_soon"
    assert body["enabled"] is True
    assert body["params"]["lead_days"] == 3


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reminder_rule_rejects_non_positive_lead_days(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """lead_days <= 0 is rejected with 422."""

    _, token = user
    response = await client.post(
        "/reminder-rules",
        json={"rule_type": "task_due_soon", "lead_days": 0},
        headers=_auth(token),
    )
    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_disable_reminder_rule(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """PATCH enabled=false disables the rule for future scheduler runs."""

    _, token = user
    create = await client.post(
        "/reminder-rules",
        json={"rule_type": "task_due_soon", "lead_days": 3},
        headers=_auth(token),
    )
    assert create.status_code == 201, create.text
    rule_id = create.json()["data"]["id"]

    response = await client.patch(
        f"/reminder-rules/{rule_id}",
        json={"enabled": False},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["enabled"] is False


# ---------------------------------------------------------------------------
# R7 — Disparo manual admin-only (Fase B)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_endpoint_admin_returns_count(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
    rbac_admin,
) -> None:
    """POST /reminders/dispatch with RBAC ADMIN runs the dispatcher and reports a count."""

    admin, admin_token = user
    await rbac_admin(session, tenant, admin)

    response = await client.post("/reminders/dispatch", headers=_auth(admin_token))

    assert response.status_code == 200, response.text
    assert isinstance(response.json()["data"]["created"], int)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_endpoint_rejects_non_admin(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """POST /reminders/dispatch without the RBAC ADMIN role responds 403."""

    _, token = user
    response = await client.post("/reminders/dispatch", headers=_auth(token))
    assert response.status_code == 403
