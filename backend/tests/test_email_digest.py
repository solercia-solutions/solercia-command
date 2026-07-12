"""Tests for the ``email_digest`` job (change 08, Fase C; adapted for change
12-notification-hub, Fase 2 — the digest now enqueues via the hub's store
port (``app.notify.store.enqueue_delivery``) onto ``notification_deliveries``
instead of instantiating ``EmailOutbox`` directly, with NO change to the
emailed_at/idempotency/dedup_key assertions below).

R4 Preferencia de digest por usuario · R5 Alcance y marcado del digest · R6
Idempotencia del envío · R8 Aislamiento multi-tenant · R9 Plantillas en
español colombiano formal (specs/email-notifications/spec.md).

Every test invokes ``dispatch_digest``/``dispatch_deliveries`` directly —
never waits for the scheduler (pattern of ``test_reminder_dispatch.py``).
Digest preferences are seeded with ``digest_hour=0`` and
``last_digest_at=None`` so the "hour reached" gate is always satisfied
regardless of wall-clock time when the suite runs.
"""

import logging

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.organizations.models import Organization
from tests.conftest import TwoOrgs, skip_no_db


class _RecordingSender:
    def __init__(self) -> None:
        self.sent: list[dict[str, str | None]] = []

    async def send(
        self, to: str, subject: str, text_body: str, html_body: str | None = None
    ) -> None:
        self.sent.append({"to": to, "subject": subject, "text_body": text_body})


class _FailingSender:
    async def send(
        self, to: str, subject: str, text_body: str, html_body: str | None = None
    ) -> None:
        raise RuntimeError("SMTP no disponible (simulado).")


async def _seed_preference(
    session: AsyncSession,
    tenant: Organization,
    user_id,
    *,
    frequency: str = "daily",
    hour: int = 0,
    weekday: int | None = None,
    last_digest_at=None,
):
    from app.modules.notifications.models import NotificationPreference
    from app.shared.enums import DigestFrequency

    pref = NotificationPreference(
        organization_id=tenant.id,
        user_id=user_id,
        digest_frequency=DigestFrequency(frequency),
        digest_hour=hour,
        digest_weekday=weekday,
        last_digest_at=last_digest_at,
    )
    session.add(pref)
    await session.flush()
    return pref


async def _seed_unread_notification(
    session: AsyncSession, tenant: Organization, user_id, *, title: str, body: str
):
    import uuid

    from app.modules.notifications.models import Notification

    notif = Notification(
        organization_id=tenant.id,
        recipient_user_id=user_id,
        rule_type="task_overdue",
        title=title,
        body=body,
        dedup_key=f"task_overdue:{uuid.uuid4().hex[:10]}",
    )
    session.add(notif)
    await session.flush()
    return notif


# ---------------------------------------------------------------------------
# R4/R5/R9 — Digest diario agrupa las no leídas sin emailed_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_digest_groups_unread_notifications_and_marks_emailed_at(
    session: AsyncSession, tenant: Organization, user, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.email.digest import dispatch_digest
    from app.modules.notifications.models import Notification, NotificationPreference
    from app.notify.models import NotificationDelivery

    owner, _ = user
    pref = await _seed_preference(session, tenant, owner.id, frequency="daily", hour=0)
    n1 = await _seed_unread_notification(
        session, tenant, owner.id, title="Mención en tarea", body="Te mencionaron."
    )
    n2 = await _seed_unread_notification(
        session, tenant, owner.id, title="Tarea vencida", body="La tarea X está vencida."
    )
    n3 = await _seed_unread_notification(
        session, tenant, owner.id, title="Recordatorio", body="No olvides revisar."
    )

    dispatched = await dispatch_digest(session)
    assert dispatched == 1

    result = await session.execute(
        select(NotificationDelivery).where(NotificationDelivery.organization_id == tenant.id)
    )
    outbox_row = result.scalar_one()
    assert outbox_row.channel == "email"
    assert outbox_row.notification_id is None
    assert outbox_row.payload["recipient_email"] == owner.email
    assert outbox_row.dedup_key.startswith(f"digest:{owner.id}:")
    for notif in (n1, n2, n3):
        assert notif.title in outbox_row.payload["text_body"]
        assert notif.body in outbox_row.payload["text_body"]

    for notif_id in (n1.id, n2.id, n3.id):
        refreshed = (
            await session.execute(select(Notification).where(Notification.id == notif_id))
        ).scalar_one()
        assert refreshed.emailed_at is not None

    refreshed_pref = (
        await session.execute(
            select(NotificationPreference).where(NotificationPreference.id == pref.id)
        )
    ).scalar_one()
    assert refreshed_pref.last_digest_at is not None


# ---------------------------------------------------------------------------
# R6 — Doble corrida no duplica (emailed_at ya marcado -> nada que digestar)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_digest_rerun_after_marking_finds_nothing_to_send(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """Exercises the R6 mechanism directly: even if the period gate were
    bypassed (``last_digest_at`` reset), the ``emailed_at IS NULL`` filter
    finds zero rows the second time, so no second email is composed."""

    from sqlalchemy import update

    from app.email.digest import dispatch_digest
    from app.modules.notifications.models import NotificationPreference
    from app.notify.models import NotificationDelivery

    owner, _ = user
    await _seed_preference(session, tenant, owner.id, frequency="daily", hour=0)
    await _seed_unread_notification(
        session, tenant, owner.id, title="Alerta", body="Algo requiere tu atención."
    )

    first = await dispatch_digest(session)
    assert first == 1

    # Simulate the period gate being satisfied again (e.g. next scheduler
    # tick after midnight) WITHOUT any new unread notification.
    await session.execute(
        update(NotificationPreference)
        .where(NotificationPreference.organization_id == tenant.id)
        .values(last_digest_at=None)
    )

    second = await dispatch_digest(session)
    assert second == 0

    result = await session.execute(
        select(NotificationDelivery).where(NotificationDelivery.organization_id == tenant.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1  # still exactly the one row from the first run


# ---------------------------------------------------------------------------
# R4 — Preferencia none nunca genera digest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_none_preference_never_generates_a_digest(
    session: AsyncSession, tenant: Organization, user
) -> None:
    from app.email.digest import dispatch_digest
    from app.notify.models import NotificationDelivery

    owner, _ = user
    await _seed_preference(session, tenant, owner.id, frequency="none")
    await _seed_unread_notification(
        session, tenant, owner.id, title="Aviso", body="Aviso de prueba."
    )

    dispatched = await dispatch_digest(session)
    assert dispatched == 0

    result = await session.execute(
        select(NotificationDelivery).where(NotificationDelivery.organization_id == tenant.id)
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# R8 — Aislamiento multi-tenant del digest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_digest_isolated_between_two_organizations(
    session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    from app.email.digest import dispatch_digest
    from app.notify.models import NotificationDelivery

    await _seed_preference(session, two_orgs.a.organization, two_orgs.a.user.id, hour=0)
    await _seed_preference(session, two_orgs.b.organization, two_orgs.b.user.id, hour=0)

    await _seed_unread_notification(
        session,
        two_orgs.a.organization,
        two_orgs.a.user.id,
        title="Solo de Org A",
        body="Contenido exclusivo de la organización A.",
    )
    await _seed_unread_notification(
        session,
        two_orgs.b.organization,
        two_orgs.b.user.id,
        title="Solo de Org B",
        body="Contenido exclusivo de la organización B.",
    )

    dispatched = await dispatch_digest(session)
    assert dispatched == 2

    result = await session.execute(select(NotificationDelivery))
    rows = {row.organization_id: row for row in result.scalars().all()}

    assert "Solo de Org A" in rows[two_orgs.a.organization.id].payload["text_body"]
    assert "Solo de Org B" not in rows[two_orgs.a.organization.id].payload["text_body"]

    assert "Solo de Org B" in rows[two_orgs.b.organization.id].payload["text_body"]
    assert "Solo de Org A" not in rows[two_orgs.b.organization.id].payload["text_body"]


# ---------------------------------------------------------------------------
# R6 — Agotamiento de reintentos del outbox del digest: notificaciones
# marcadas NO se re-digestan pero siguen visibles vía GET /notifications
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_digest_outbox_exhausted_retries_notifications_stay_visible(
    client,
    session: AsyncSession,
    tenant: Organization,
    user,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.email.digest import dispatch_digest
    from app.notify.dispatcher import dispatch_deliveries
    from app.notify.models import NotificationDelivery
    from app.shared.enums import EmailOutboxStatus

    owner, token = user
    await _seed_preference(session, tenant, owner.id, frequency="daily", hour=0)
    notif = await _seed_unread_notification(
        session, tenant, owner.id, title="Riesgo", body="Tarea en riesgo."
    )

    dispatched = await dispatch_digest(session)
    assert dispatched == 1

    monkeypatch.setattr(settings, "EMAIL_MAX_ATTEMPTS", 1)
    monkeypatch.setattr("app.email.outbox.get_email_sender", lambda: _FailingSender())

    with caplog.at_level(logging.ERROR, logger="solercia.notify.dispatcher"):
        await dispatch_deliveries(session)

    result = await session.execute(
        select(NotificationDelivery).where(NotificationDelivery.organization_id == tenant.id)
    )
    outbox_row = result.scalar_one()
    assert outbox_row.status == EmailOutboxStatus.failed
    assert outbox_row.dedup_key in caplog.text

    # The notification stays marked (never "un-digested") AND stays visible
    # via REST — the source of truth is never lost.
    response = await client.get(
        "/notifications", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["data"]}
    assert str(notif.id) in ids
