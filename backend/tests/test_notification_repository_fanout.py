"""Tests for the channel fan-out in ``NotificationRepository.create()``
(change 12-notification-hub, Fase 2, D2/R2).

R2 Fan-out único con aislamiento de fallos entre canales
(specs/notification-hub/spec.md).

Fake durable/best_effort channels are registered via the snapshot/restore
fixture (pattern of ``test_notify_registry.py``) so the fan-out is exercised
without touching real email/websocket infrastructure. Approval-testing
angle (strict-tdd, "refactoring existing code"): ``create()`` already
existed with 2 hardcoded calls before this change — these tests describe
its NEW, registry-driven behavior.
"""

import logging
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.notify import registry
from app.notify.ports import DeliveryPolicy
from tests.conftest import skip_no_db


class _FakeDurableChannel:
    def __init__(self, name: str = "fake-durable") -> None:
        self.name = name
        self.policy = DeliveryPolicy.durable
        self.enqueued: list = []

    async def enqueue(self, db, notification) -> None:
        self.enqueued.append(notification.id)


class _FakeBestEffortChannel:
    def __init__(self, name: str = "fake-best-effort") -> None:
        self.name = name
        self.policy = DeliveryPolicy.best_effort
        self.buffered: list = []

    def buffer(self, db, notification) -> None:
        self.buffered.append(notification.id)


class _FakeRaisingDurableChannel:
    """Registered ALONGSIDE a healthy channel to prove failure isolation."""

    def __init__(self, name: str = "fake-broken") -> None:
        self.name = name
        self.policy = DeliveryPolicy.durable

    async def enqueue(self, db, notification) -> None:
        raise RuntimeError("Canal roto (simulado).")


@pytest.fixture(autouse=True)
def _snapshot_channels():
    original = list(registry._CHANNELS)
    yield
    registry._CHANNELS[:] = original


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_iterates_registered_channels_by_policy(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A registered ``durable`` channel gets ``enqueue``, a ``best_effort``
    one gets ``buffer`` — the core reads behavior from the registry, not a
    hardcoded pair of calls (spec ``notification-hub``, "Fan-out único")."""

    from app.modules.notifications.repository import NotificationRepository

    durable = _FakeDurableChannel()
    best_effort = _FakeBestEffortChannel()
    registry.register_channel(durable)
    registry.register_channel(best_effort)

    owner, _ = user
    repo = NotificationRepository(session)
    notification = await repo.create(
        organization_id=tenant.id,
        recipient_user_id=owner.id,
        rule_type="task_overdue",
        title="Fan-out test",
        body="Cuerpo de prueba.",
        dedup_key=f"task_overdue:fanout-{uuid.uuid4().hex[:8]}",
    )

    assert durable.enqueued == [notification.id]
    assert best_effort.buffered == [notification.id]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_isolates_a_failing_channel_from_the_healthy_one_and_the_tx(
    session: AsyncSession,
    tenant: Organization,
    user,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A channel that raises during fan-out MUST NOT: (1) stop the healthy
    channel from receiving the notification, (2) break the notification's
    own persistence/transaction. Only an ERROR is logged (gate correction —
    isolation between channels)."""

    from app.modules.notifications.models import Notification
    from app.modules.notifications.repository import NotificationRepository

    healthy = _FakeDurableChannel("fake-healthy")
    broken = _FakeRaisingDurableChannel()
    registry.register_channel(broken)
    registry.register_channel(healthy)

    owner, _ = user
    repo = NotificationRepository(session)
    with caplog.at_level(logging.ERROR, logger="solercia.notifications.repository"):
        notification = await repo.create(
            organization_id=tenant.id,
            recipient_user_id=owner.id,
            rule_type="task_overdue",
            title="Isolation test",
            body="Cuerpo de prueba.",
            dedup_key=f"task_overdue:isolation-{uuid.uuid4().hex[:8]}",
        )

    assert healthy.enqueued == [notification.id]
    assert "fake-broken" in caplog.text

    # The business transaction that created the Notification survives the
    # broken channel's exception: an explicit commit + re-read proves it.
    await session.commit()
    result = await session.execute(
        select(Notification).where(Notification.id == notification.id)
    )
    assert result.scalar_one().id == notification.id
