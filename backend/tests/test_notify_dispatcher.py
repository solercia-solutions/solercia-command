"""Tests for the generic delivery dispatcher (``app.notify.dispatcher``,
change 12-notification-hub, Fase 2, D3).

R3 Entrega durable en ``notification_deliveries`` (claim atómico, reintentos,
``failed`` terminal, idempotencia) — generalized across channels
(specs/notification-hub/spec.md).

Every test invokes ``dispatch_deliveries`` directly — never waits for the
scheduler (pattern of ``test_reminder_dispatch.py``/``test_email_dispatch.py``).
Fake durable channels are registered via the snapshot/restore fixture
(pattern of ``test_notify_registry.py``) so tests control success/failure
deterministically without touching email/SMTP.
"""

import logging
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.organizations.models import Organization
from app.notify import registry
from app.notify.ports import DeliveryPolicy
from tests.conftest import TwoOrgs, skip_no_db


class _FakeDurableChannel:
    """A durable channel whose ``deliver`` outcome is fully test-controlled."""

    def __init__(self, name: str = "fake-durable", *, fail: bool = False) -> None:
        self.name = name
        self.policy = DeliveryPolicy.durable
        self.fail = fail
        self.delivered: list[dict] = []

    async def deliver(self, payload: dict) -> None:
        if self.fail:
            raise RuntimeError("Canal fake caído (simulado).")
        self.delivered.append(payload)


@pytest.fixture(autouse=True)
def _snapshot_channels():
    original = list(registry._CHANNELS)
    yield
    registry._CHANNELS[:] = original


async def _seed_pending_delivery(
    session: AsyncSession,
    tenant: Organization,
    *,
    channel: str,
    dedup_key: str,
    payload: dict | None = None,
    attempts: int = 0,
):
    from app.notify.models import NotificationDelivery
    from app.notify.store import enqueue_delivery

    await enqueue_delivery(
        session,
        channel=channel,
        notification_id=None,
        organization_id=tenant.id,
        dedup_key=dedup_key,
        payload=payload or {"recipient_email": "x@example.com"},
    )
    await session.flush()

    result = await session.execute(
        select(NotificationDelivery).where(NotificationDelivery.dedup_key == dedup_key)
    )
    row = result.scalar_one()
    if attempts:
        row.attempts = attempts
        session.add(row)
        await session.flush()
    return row


# ---------------------------------------------------------------------------
# Claim atómico antes de enviar (filas pending de distintos canales)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_claims_before_sending_across_distinct_channels(
    session: AsyncSession, tenant: Organization
) -> None:
    from app.notify.dispatcher import dispatch_deliveries
    from app.notify.models import NotificationDelivery
    from app.shared.enums import DeliveryStatus

    channel_a = _FakeDurableChannel("fake-a")
    channel_b = _FakeDurableChannel("fake-b")
    registry.register_channel(channel_a)
    registry.register_channel(channel_b)

    row_a = await _seed_pending_delivery(
        session,
        tenant,
        channel="fake-a",
        dedup_key="dispatch-test:a",
        payload={"marker": "a"},
    )
    row_b = await _seed_pending_delivery(
        session,
        tenant,
        channel="fake-b",
        dedup_key="dispatch-test:b",
        payload={"marker": "b"},
    )

    processed = await dispatch_deliveries(session)
    assert processed == 2

    assert channel_a.delivered == [{"marker": "a"}]
    assert channel_b.delivered == [{"marker": "b"}]

    result = await session.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.id.in_([row_a.id, row_b.id])
        )
    )
    rows = {row.channel: row for row in result.scalars().all()}
    assert rows["fake-a"].status == DeliveryStatus.sent
    assert rows["fake-a"].attempts == 1
    assert rows["fake-b"].status == DeliveryStatus.sent
    assert rows["fake-b"].attempts == 1


# ---------------------------------------------------------------------------
# Agotamiento de reintentos -> failed terminal + log ERROR (solo dedup_key)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_exhausted_retries_ends_failed_with_dedup_key_only_in_log(
    session: AsyncSession,
    tenant: Organization,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.notify.dispatcher import dispatch_deliveries
    from app.notify.models import NotificationDelivery
    from app.shared.enums import DeliveryStatus

    monkeypatch.setattr(settings, "EMAIL_MAX_ATTEMPTS", 2)
    failing = _FakeDurableChannel("fake-failing", fail=True)
    registry.register_channel(failing)

    dedup_key = f"dispatch-test:exhaust-{uuid.uuid4().hex[:8]}"
    row = await _seed_pending_delivery(
        session,
        tenant,
        channel="fake-failing",
        dedup_key=dedup_key,
        payload={"recipient_email": "secreto@example.com"},
        attempts=1,
    )

    with caplog.at_level(logging.ERROR, logger="solercia.notify.dispatcher"):
        processed = await dispatch_deliveries(session)
    assert processed == 1

    result = await session.execute(
        select(NotificationDelivery).where(NotificationDelivery.id == row.id)
    )
    refreshed = result.scalar_one()
    assert refreshed.status == DeliveryStatus.failed
    assert refreshed.attempts == 2
    assert dedup_key in caplog.text
    assert "secreto@example.com" not in caplog.text  # payload NEVER leaks into the log

    second_processed = await dispatch_deliveries(session)
    result = await session.execute(
        select(NotificationDelivery).where(NotificationDelivery.id == row.id)
    )
    still_failed = result.scalar_one()
    assert still_failed.status == DeliveryStatus.failed
    assert still_failed.attempts == 2  # unchanged — never reclaimed once failed
    assert second_processed == 0


# ---------------------------------------------------------------------------
# Re-corrida sobre fila sent no reintenta ni duplica
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_rerun_over_sent_row_does_not_resend(
    session: AsyncSession, tenant: Organization
) -> None:
    from app.notify.dispatcher import dispatch_deliveries
    from app.notify.models import NotificationDelivery
    from app.shared.enums import DeliveryStatus

    channel = _FakeDurableChannel("fake-idempotent")
    registry.register_channel(channel)

    await _seed_pending_delivery(
        session,
        tenant,
        channel="fake-idempotent",
        dedup_key="dispatch-test:idempotent",
    )

    first = await dispatch_deliveries(session)
    assert first == 1
    assert len(channel.delivered) == 1

    second = await dispatch_deliveries(session)
    assert second == 0
    assert len(channel.delivered) == 1  # no second send

    result = await session.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.dedup_key == "dispatch-test:idempotent"
        )
    )
    assert result.scalar_one().status == DeliveryStatus.sent


# ---------------------------------------------------------------------------
# Aislamiento multi-tenant entre filas de distintas organizaciones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_never_crosses_organization_boundaries(
    session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    from app.notify.dispatcher import dispatch_deliveries
    from app.notify.models import NotificationDelivery
    from app.shared.enums import DeliveryStatus

    channel = _FakeDurableChannel("fake-tenant")
    registry.register_channel(channel)

    row_a = await _seed_pending_delivery(
        session,
        two_orgs.a.organization,
        channel="fake-tenant",
        dedup_key="dispatch-test:tenant-a",
        payload={"org": "a"},
    )
    row_b = await _seed_pending_delivery(
        session,
        two_orgs.b.organization,
        channel="fake-tenant",
        dedup_key="dispatch-test:tenant-b",
        payload={"org": "b"},
    )

    processed = await dispatch_deliveries(session)
    assert processed == 2

    result = await session.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.id.in_([row_a.id, row_b.id])
        )
    )
    rows = {row.organization_id: row for row in result.scalars().all()}

    assert rows[two_orgs.a.organization.id].status == DeliveryStatus.sent
    assert rows[two_orgs.b.organization.id].status == DeliveryStatus.sent

    delivered_orgs = {p["org"] for p in channel.delivered}
    assert delivered_orgs == {"a", "b"}
