"""Tests for in-app notifications (/notifications).

R1 ``GET /notifications`` solo trae las del usuario · R2 dedup — un
``dedup_key`` activo bloquea un duplicado · R3 ``unread-count`` solo cuenta
``active`` · R4 ``PATCH /notifications/{id}`` cambia ``status`` sin borrado
(openspec/specs/notifications-inapp/spec.md).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.shared.enums import MemberRole
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_notification(
    session: AsyncSession,
    tenant: Organization,
    recipient_id: uuid.UUID,
    *,
    status: str = "active",
    dedup_key: str | None = None,
):
    from app.modules.notifications.models import Notification

    notification = Notification(
        organization_id=tenant.id,
        recipient_user_id=recipient_id,
        rule_type="task_overdue",
        title="Test notification",
        body="Body",
        dedup_key=dedup_key or f"task_overdue:{uuid.uuid4().hex[:8]}",
        status=status,
    )
    session.add(notification)
    await session.flush()
    return notification


# ---------------------------------------------------------------------------
# R1 — Bandeja propia: solo las del usuario
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_notifications_only_returns_the_caller_own(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, make_member
) -> None:
    """A user's ``GET /notifications`` never includes another member's entries."""

    from app.shared.enums import MemberRole

    owner, token = user
    other_user, _ = await make_member(session, tenant, MemberRole.member)

    own_notification = await _seed_notification(session, tenant, owner.id)
    await _seed_notification(session, tenant, other_user.id)

    response = await client.get("/notifications", headers=_auth(token))

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert ids == {str(own_notification.id)}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_notifications_never_crosses_organizations(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """org A's user never sees a notification whose ``organization_id``
    belongs to org B — aislamiento entre tenants (``two_orgs``).
    """

    response = await client.get("/notifications", headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert str(two_orgs.a.notification.id) in ids
    assert str(two_orgs.b.notification.id) not in ids


# ---------------------------------------------------------------------------
# R2 — Deduplicación por dedup_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_exists_active_guards_against_duplicate_dedup_key(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """``exists_active`` reports True while an active notification with that
    ``dedup_key`` exists, and False for an unrelated key — the guard the
    evaluator relies on (test_alert_engine.py exercises it end-to-end).
    """

    from app.modules.notifications.repository import NotificationRepository

    owner, _ = user
    await _seed_notification(
        session, tenant, owner.id, dedup_key="task_overdue:T1:U1"
    )

    repo = NotificationRepository(session)

    assert await repo.exists_active(tenant.id, "task_overdue:T1:U1") is True
    assert await repo.exists_active(tenant.id, "task_overdue:T2:U1") is False


# ---------------------------------------------------------------------------
# R3 — unread-count solo cuenta active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_unread_count_only_counts_active_status(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user
) -> None:
    """``unread-count`` counts ONLY ``active`` notifications, ignoring
    ``read``/``resolved``/``silenced`` ones for the same user.
    """

    owner, token = user
    await _seed_notification(session, tenant, owner.id, status="active")
    await _seed_notification(session, tenant, owner.id, status="active")
    await _seed_notification(session, tenant, owner.id, status="read")
    await _seed_notification(session, tenant, owner.id, status="resolved")

    response = await client.get("/notifications/unread-count", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert response.json()["data"]["count"] == 2


# ---------------------------------------------------------------------------
# R4 — PATCH cambia status sin borrado; unread-count baja
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_notification_changes_status_and_lowers_unread_count(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user
) -> None:
    """PATCH to ``read`` updates ``status`` (row survives, no delete) and the
    unread-count drops by one.
    """

    from sqlalchemy import select

    from app.modules.notifications.models import Notification

    owner, token = user
    notification = await _seed_notification(session, tenant, owner.id, status="active")

    before = await client.get("/notifications/unread-count", headers=_auth(token))
    assert before.json()["data"]["count"] == 1

    response = await client.patch(
        f"/notifications/{notification.id}",
        json={"status": "read"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "read"

    row = (
        await session.execute(
            select(Notification).where(Notification.id == notification.id)
        )
    ).scalar_one()
    assert row.status.value == "read"

    after = await client.get("/notifications/unread-count", headers=_auth(token))
    assert after.json()["data"]["count"] == 0


# ---------------------------------------------------------------------------
# Matriz de permisos — GET /notifications: sin gate de rol
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role", [MemberRole.admin, MemberRole.manager, MemberRole.member, MemberRole.viewer]
)
@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_notifications_has_no_role_gate(
    role: MemberRole,
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    make_member,
) -> None:
    """Every ``MemberRole`` — including ``viewer`` — gets 2xx from
    ``GET /notifications``: only authentication + membership, no role gate.
    """

    _, token = await make_member(session, tenant, role)

    response = await client.get("/notifications", headers=_auth(token))

    assert response.status_code == 200, response.text
