"""Tests for the delivery store port (``app.notify.store.enqueue_delivery``,
change 12-notification-hub, Fase 1, D3).

R3 Entrega durable en ``notification_deliveries`` (claim atómico, reintentos,
``failed`` terminal, idempotencia) — specifically the INSERT half: no
``commit()`` of its own (same contract as the ``EmailOutbox`` insert it
replaces, change 08 D2), and ``dedup_key`` is enforced UNIQUE.

Uses the SAVEPOINT ``session`` fixture, mirroring ``test_reminder_dispatch.py``.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from tests.conftest import skip_no_db


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_enqueue_delivery_inserts_pending_row_with_given_fields(
    session: AsyncSession, tenant: Organization
) -> None:
    """A pending row is inserted with the exact channel/payload/dedup_key
    given, scoped to the caller's organization."""

    from app.notify.models import NotificationDelivery
    from app.notify.store import enqueue_delivery
    from app.shared.enums import DeliveryStatus

    await enqueue_delivery(
        session,
        channel="email",
        notification_id=None,
        organization_id=tenant.id,
        dedup_key="test-store:pending-row",
        payload={"recipient_email": "a@example.com", "subject": "Asunto"},
    )

    result = await session.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.dedup_key == "test-store:pending-row"
        )
    )
    row = result.scalar_one()
    assert row.channel == "email"
    assert row.status == DeliveryStatus.pending
    assert row.organization_id == tenant.id
    assert row.notification_id is None
    assert row.payload == {"recipient_email": "a@example.com", "subject": "Asunto"}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_enqueue_delivery_rollback_reverts_without_its_own_commit(
    session: AsyncSession, tenant: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two REAL proofs of the transactional contract: (1) ``commit()`` is
    NEVER called by ``enqueue_delivery`` itself — the guard raises if it is;
    (2) the caller's own ``rollback()`` reverts the insert, proving it never
    escaped the active transaction via a commit the guard might have missed."""

    from app.notify.models import NotificationDelivery
    from app.notify.store import enqueue_delivery

    async def _forbidden_commit() -> None:
        raise AssertionError("enqueue_delivery must not commit its own transaction")

    monkeypatch.setattr(session, "commit", _forbidden_commit)

    await enqueue_delivery(
        session,
        channel="email",
        notification_id=None,
        organization_id=tenant.id,
        dedup_key="test-store:rollback-reverts",
        payload={"recipient_email": "b@example.com"},
    )
    await session.flush()

    visible = await session.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.dedup_key == "test-store:rollback-reverts"
        )
    )
    assert visible.scalar_one_or_none() is not None

    await session.rollback()

    reverted = await session.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.dedup_key == "test-store:rollback-reverts"
        )
    )
    assert reverted.scalar_one_or_none() is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_enqueue_delivery_duplicate_dedup_key_violates_unique_index(
    session: AsyncSession, tenant: Organization
) -> None:
    """A second call with the SAME ``dedup_key`` violates the unique index —
    the idempotency guard the dispatcher relies on."""

    from app.notify.store import enqueue_delivery

    await enqueue_delivery(
        session,
        channel="email",
        notification_id=None,
        organization_id=tenant.id,
        dedup_key="test-store:duplicate",
        payload={"recipient_email": "c@example.com"},
    )
    await session.flush()

    await enqueue_delivery(
        session,
        channel="email",
        notification_id=None,
        organization_id=tenant.id,
        dedup_key="test-store:duplicate",
        payload={"recipient_email": "d@example.com"},
    )
    with pytest.raises(IntegrityError):
        await session.flush()
