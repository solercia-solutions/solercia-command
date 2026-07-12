"""Tests for the ``email`` channel's ``deliver`` via the generic dispatcher
(change 08, Fase B; adapted for change 12-notification-hub, Fase 2 —
``dispatch_outbox`` -> ``dispatch_deliveries``, ``EmailOutbox`` ->
``NotificationDelivery`` with ``channel``/``payload``, NO change to the
status/attempts/sent_at assertions below).

R1 Puerto EmailSender agnóstico · R3 Envío inmediato de tipos urgentes ·
R6 Idempotencia del envío · R8 Aislamiento multi-tenant
(specs/email-notifications/spec.md).

Every test invokes ``dispatch_deliveries`` directly — never waits for the
scheduler (pattern of ``test_reminder_dispatch.py``). The concrete
``EmailSender`` is swapped via monkeypatching ``app.email.outbox.
get_email_sender`` so tests control success/failure deterministically
without touching the network — ``EmailChannel.deliver`` (registered in
``app.email.outbox``) is the only place that calls it.
"""

import logging
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.organizations.models import Organization
from tests.conftest import TwoOrgs, skip_no_db


class _RecordingSender:
    """Always succeeds; records every call for assertions."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str | None]] = []

    async def send(
        self, to: str, subject: str, text_body: str, html_body: str | None = None
    ) -> None:
        self.sent.append({"to": to, "subject": subject, "text_body": text_body})


class _FailingSender:
    """Always raises — simulates an SMTP backend that is down."""

    async def send(
        self, to: str, subject: str, text_body: str, html_body: str | None = None
    ) -> None:
        raise RuntimeError("SMTP no disponible (simulado).")


async def _seed_outbox_row(
    session: AsyncSession,
    tenant: Organization,
    *,
    dedup_key: str,
    recipient_email: str = "recipient@example.com",
    attempts: int = 0,
    status: str | None = None,
):
    from app.notify.models import NotificationDelivery
    from app.shared.enums import EmailOutboxStatus

    row = NotificationDelivery(
        organization_id=tenant.id,
        notification_id=None,
        channel="email",
        payload={
            "recipient_email": recipient_email,
            "subject": "Asunto de prueba",
            "text_body": "Cuerpo de prueba.",
            "html_body": "<p>Cuerpo de prueba.</p>",
        },
        dedup_key=dedup_key,
        status=status or EmailOutboxStatus.pending,
        attempts=attempts,
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# R1/R3 — Despacho exitoso de una fila pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_sends_pending_row_and_marks_sent(
    session: AsyncSession, tenant: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.notify.dispatcher import dispatch_deliveries
    from app.notify.models import NotificationDelivery
    from app.shared.enums import EmailOutboxStatus

    sender = _RecordingSender()
    monkeypatch.setattr("app.email.outbox.get_email_sender", lambda: sender)

    row = await _seed_outbox_row(
        session, tenant, dedup_key="immediate:dispatch-test-1", recipient_email="ana@example.com"
    )

    processed = await dispatch_deliveries(session)
    assert processed == 1

    assert len(sender.sent) == 1
    assert sender.sent[0]["to"] == "ana@example.com"

    result = await session.execute(
        select(NotificationDelivery).where(NotificationDelivery.id == row.id)
    )
    refreshed = result.scalar_one()
    assert refreshed.status == EmailOutboxStatus.sent
    assert refreshed.sent_at is not None
    assert refreshed.attempts == 1


# ---------------------------------------------------------------------------
# R3 — Fallo de envío no rompe la operación de negocio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_failure_leaves_row_pending_and_retryable(
    session: AsyncSession, tenant: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A send failure (attempts below EMAIL_MAX_ATTEMPTS) leaves the row
    ``pending`` again, ready for the next dispatch cycle — never lost."""

    from app.notify.dispatcher import dispatch_deliveries
    from app.notify.models import NotificationDelivery
    from app.shared.enums import EmailOutboxStatus

    monkeypatch.setattr(settings, "EMAIL_MAX_ATTEMPTS", 5)
    monkeypatch.setattr("app.email.outbox.get_email_sender", lambda: _FailingSender())

    row = await _seed_outbox_row(session, tenant, dedup_key="immediate:dispatch-test-2")

    processed = await dispatch_deliveries(session)
    assert processed == 1

    result = await session.execute(
        select(NotificationDelivery).where(NotificationDelivery.id == row.id)
    )
    refreshed = result.scalar_one()
    assert refreshed.status == EmailOutboxStatus.pending
    assert refreshed.attempts == 1
    assert refreshed.last_error is not None


# ---------------------------------------------------------------------------
# R6 — Agotamiento de reintentos termina en failed + log ERROR, sin duplicar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_exhausted_retries_ends_in_failed_with_error_log(
    session: AsyncSession,
    tenant: Organization,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.notify.dispatcher import dispatch_deliveries
    from app.notify.models import NotificationDelivery
    from app.shared.enums import EmailOutboxStatus

    monkeypatch.setattr(settings, "EMAIL_MAX_ATTEMPTS", 2)
    monkeypatch.setattr("app.email.outbox.get_email_sender", lambda: _FailingSender())

    dedup_key = f"digest:exhaust-test-{uuid.uuid4().hex[:8]}"
    row = await _seed_outbox_row(session, tenant, dedup_key=dedup_key, attempts=1)

    with caplog.at_level(logging.ERROR, logger="solercia.notify.dispatcher"):
        processed = await dispatch_deliveries(session)
    assert processed == 1

    result = await session.execute(
        select(NotificationDelivery).where(NotificationDelivery.id == row.id)
    )
    refreshed = result.scalar_one()
    assert refreshed.status == EmailOutboxStatus.failed
    assert refreshed.attempts == 2
    assert dedup_key in caplog.text

    # No further reintent: a second dispatch run finds nothing pending for this row.
    second_processed = await dispatch_deliveries(session)
    result = await session.execute(
        select(NotificationDelivery).where(NotificationDelivery.id == row.id)
    )
    still_failed = result.scalar_one()
    assert still_failed.status == EmailOutboxStatus.failed
    assert still_failed.attempts == 2  # unchanged — never reclaimed once failed
    assert second_processed == 0


# ---------------------------------------------------------------------------
# R6 — Reintento de fila pending con attempts>0 no duplica dedup_key/fila
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_retry_reuses_same_dedup_key_no_duplicate_row(
    session: AsyncSession, tenant: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.notify.dispatcher import dispatch_deliveries
    from app.notify.models import NotificationDelivery
    from app.shared.enums import EmailOutboxStatus

    sender = _RecordingSender()
    monkeypatch.setattr("app.email.outbox.get_email_sender", lambda: sender)

    dedup_key = "immediate:dispatch-test-retry"
    await _seed_outbox_row(session, tenant, dedup_key=dedup_key, attempts=1)

    await dispatch_deliveries(session)

    result = await session.execute(
        select(NotificationDelivery).where(NotificationDelivery.dedup_key == dedup_key)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].status == EmailOutboxStatus.sent
    assert rows[0].attempts == 2
    assert len(sender.sent) == 1


# ---------------------------------------------------------------------------
# R8 — Aislamiento multi-tenant del outbox
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_never_crosses_organization_boundaries(
    session: AsyncSession, two_orgs: TwoOrgs, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.notify.dispatcher import dispatch_deliveries
    from app.notify.models import NotificationDelivery
    from app.shared.enums import EmailOutboxStatus

    sender = _RecordingSender()
    monkeypatch.setattr("app.email.outbox.get_email_sender", lambda: sender)

    row_a = await _seed_outbox_row(
        session,
        two_orgs.a.organization,
        dedup_key="immediate:tenant-test-a",
        recipient_email="a@org-a.example.com",
    )
    row_b = await _seed_outbox_row(
        session,
        two_orgs.b.organization,
        dedup_key="immediate:tenant-test-b",
        recipient_email="b@org-b.example.com",
    )

    processed = await dispatch_deliveries(session)
    assert processed == 2

    result = await session.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.id.in_([row_a.id, row_b.id])
        )
    )
    rows = {row.id: row for row in result.scalars().all()}

    assert rows[row_a.id].organization_id == two_orgs.a.organization.id
    assert rows[row_a.id].payload["recipient_email"] == "a@org-a.example.com"
    assert rows[row_a.id].status == EmailOutboxStatus.sent

    assert rows[row_b.id].organization_id == two_orgs.b.organization.id
    assert rows[row_b.id].payload["recipient_email"] == "b@org-b.example.com"
    assert rows[row_b.id].status == EmailOutboxStatus.sent

    recipients = {entry["to"] for entry in sender.sent}
    assert recipients == {"a@org-a.example.com", "b@org-b.example.com"}
