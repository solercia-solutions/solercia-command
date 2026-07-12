"""Tests for ``GET /notifications/{id}/deliveries`` (change 12-notification-hub,
Fase 3, D6).

R4 Auditoría `GET /{id}/deliveries` (admin/manager, SIN excepción de dueño,
aislamiento por organización) · R5 Tolerancia a la atribución de entregas de
digest (specs/notification-hub/spec.md).
"""

import uuid
from datetime import UTC, datetime

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
    emailed_at=None,
):
    from app.modules.notifications.models import Notification

    notification = Notification(
        organization_id=tenant.id,
        recipient_user_id=recipient_id,
        rule_type="license_expired",
        title="Licencia vencida",
        body="Cuerpo de prueba.",
        dedup_key=f"license_expired:{uuid.uuid4().hex[:10]}",
        emailed_at=emailed_at,
    )
    session.add(notification)
    await session.flush()
    return notification


async def _seed_immediate_delivery(
    session: AsyncSession, tenant: Organization, notification_id: uuid.UUID
) -> None:
    from app.notify.store import enqueue_delivery

    await enqueue_delivery(
        session,
        channel="email",
        notification_id=notification_id,
        organization_id=tenant.id,
        dedup_key=f"immediate:{notification_id}",
        payload={
            "recipient_email": "owner@example.com",
            "subject": "Asunto",
            "text_body": "Cuerpo",
            "html_body": None,
        },
    )
    await session.flush()


# ---------------------------------------------------------------------------
# Matriz de permisos — SOLO admin/manager, SIN excepción de dueño
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", [MemberRole.member, MemberRole.viewer])
@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_and_viewer_get_403_including_the_owner(
    role: MemberRole,
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    make_member,
) -> None:
    """A member/viewer never gets deliveries — even when they OWN the
    notification (D6 corregido, SIN excepción de dueño)."""

    owner, token = await make_member(session, tenant, role)
    notification = await _seed_notification(session, tenant, owner.id)

    response = await client.get(
        f"/notifications/{notification.id}/deliveries", headers=_auth(token)
    )

    assert response.status_code == 403, response.text


@pytest.mark.parametrize("role", [MemberRole.admin, MemberRole.manager])
@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_admin_and_manager_list_immediate_delivery(
    role: MemberRole,
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user,
    make_member,
) -> None:
    """An admin/manager (NOT necessarily the owner) sees the immediate
    delivery's channel/status/attempts/last_error."""

    owner, _ = user
    _, requester_token = await make_member(session, tenant, role)
    notification = await _seed_notification(session, tenant, owner.id)
    await _seed_immediate_delivery(session, tenant, notification.id)

    response = await client.get(
        f"/notifications/{notification.id}/deliveries",
        headers=_auth(requester_token),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["digested"] is False
    assert len(data["deliveries"]) == 1
    delivery = data["deliveries"][0]
    assert delivery["channel"] == "email"
    assert delivery["status"] == "pending"
    assert delivery["attempts"] == 0
    assert delivery["last_error"] is None


# ---------------------------------------------------------------------------
# R5 — Tolerancia a la atribución de entregas de digest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_digested_notification_reports_digested_true_without_immediate_row(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user,
    make_member,
) -> None:
    """A notification the digest already covered (``emailed_at`` marker, no
    immediate row) reports ``digested=true`` and an EMPTY deliveries list."""

    owner, _ = user
    _, admin_token = await make_member(session, tenant, MemberRole.admin)
    notification = await _seed_notification(
        session, tenant, owner.id, emailed_at=datetime.now(UTC)
    )

    response = await client.get(
        f"/notifications/{notification.id}/deliveries", headers=_auth(admin_token)
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["digested"] is True
    assert data["deliveries"] == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_immediate_delivery_attribution_is_exact_not_mixed_across_notifications(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user,
    make_member,
) -> None:
    """Triangulation: TWO notifications each with their OWN immediate row —
    querying one never returns the other's delivery (exact 1:1 attribution)."""

    owner, _ = user
    _, admin_token = await make_member(session, tenant, MemberRole.admin)

    notification_a = await _seed_notification(session, tenant, owner.id)
    notification_b = await _seed_notification(session, tenant, owner.id)
    await _seed_immediate_delivery(session, tenant, notification_a.id)
    await _seed_immediate_delivery(session, tenant, notification_b.id)

    response = await client.get(
        f"/notifications/{notification_a.id}/deliveries", headers=_auth(admin_token)
    )

    assert response.status_code == 200, response.text
    assert len(response.json()["data"]["deliveries"]) == 1


# ---------------------------------------------------------------------------
# best_effort (websocket) nunca aparece en la auditoría
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_best_effort_channel_never_appears_in_deliveries(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user,
    make_member,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The REAL fan-out reaches BOTH the durable email channel and the
    best_effort websocket channel, but only the durable one ever appears in
    the audit — best_effort, by definition, has no store row."""

    from app.config import settings
    from app.modules.notifications.repository import NotificationRepository

    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)

    owner, _ = user
    _, admin_token = await make_member(session, tenant, MemberRole.admin)

    repo = NotificationRepository(session)
    notification = await repo.create(
        organization_id=tenant.id,
        recipient_user_id=owner.id,
        rule_type="license_expired",
        title="Licencia vencida",
        body="Cuerpo.",
        dedup_key=f"license_expired:{uuid.uuid4().hex[:10]}",
    )

    response = await client.get(
        f"/notifications/{notification.id}/deliveries", headers=_auth(admin_token)
    )

    assert response.status_code == 200, response.text
    channels = {d["channel"] for d in response.json()["data"]["deliveries"]}
    assert channels == {"email"}


# ---------------------------------------------------------------------------
# Aislamiento entre organizaciones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_cross_organization_notification_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """An org B admin querying an org A notification's deliveries gets 404 —
    never a cross-tenant leak."""

    _, admin_token = await make_member(session, two_orgs.b.organization, MemberRole.admin)

    response = await client.get(
        f"/notifications/{two_orgs.a.notification.id}/deliveries",
        headers=_auth(admin_token),
    )

    assert response.status_code == 404, response.text
