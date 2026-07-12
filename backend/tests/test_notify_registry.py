"""Tests for the delivery channel registry (``app.notify.registry``, change
12-notification-hub, Fase 2, D1/D6).

R1 Puerto DeliveryChannel y registro extensible sin tocar el núcleo · R6
Extensibilidad para canales futuros sin tocar el núcleo
(specs/notification-hub/spec.md, "Canal de prueba recibe el fan-out sin
tocar el núcleo").

A ``fake`` channel registered ONLY for a test proves the registry is
extensible without touching the hub's core: no production module needs to
change for a new channel to be recognized.
"""

import pytest

from app.notify import registry
from app.notify.ports import DeliveryPolicy


@pytest.fixture(autouse=True)
def _snapshot_channels():
    """Snapshot ``registry._CHANNELS`` before each test and restore after,
    so a test-only fake channel never leaks into another test/module."""

    original = list(registry._CHANNELS)
    yield
    registry._CHANNELS[:] = original


class _FakeBestEffortChannel:
    """A minimal ``best_effort`` channel, registered ONLY for these tests."""

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.policy = DeliveryPolicy.best_effort
        self.buffered: list = []

    def buffer(self, db, notification) -> None:
        self.buffered.append(notification)


class _FakeDurableChannel:
    """A minimal ``durable`` channel, registered ONLY for these tests."""

    def __init__(self, name: str = "fake-durable") -> None:
        self.name = name
        self.policy = DeliveryPolicy.durable

    async def enqueue(self, db, notification) -> None:
        pass

    async def deliver(self, payload: dict) -> None:
        pass


def test_register_channel_appears_in_get_channels() -> None:
    """A channel registered only for this test shows up in ``get_channels()``
    without any core module needing to change."""

    fake = _FakeBestEffortChannel()
    before = registry.get_channels()
    assert fake not in before

    registry.register_channel(fake)

    after = registry.get_channels()
    assert fake in after
    assert len(after) == len(before) + 1


def test_get_channels_partitions_by_policy() -> None:
    """Triangulation: a SECOND, differently-policied fake channel proves the
    registry does not hardcode a single policy — both are retrievable and
    distinguishable by ``.policy``."""

    durable = _FakeDurableChannel()
    best_effort = _FakeBestEffortChannel(name="fake-2")
    registry.register_channel(durable)
    registry.register_channel(best_effort)

    channels = registry.get_channels()
    durable_names = {c.name for c in channels if c.policy == DeliveryPolicy.durable}
    best_effort_names = {
        c.name for c in channels if c.policy == DeliveryPolicy.best_effort
    }
    assert "fake-durable" in durable_names
    assert "fake-2" in best_effort_names


def test_get_channels_returns_an_independent_snapshot() -> None:
    """Mutating the list returned by ``get_channels()`` MUST NOT mutate the
    registry's own internal state."""

    fake = _FakeBestEffortChannel()
    registry.register_channel(fake)

    snapshot = registry.get_channels()
    snapshot.append(_FakeBestEffortChannel(name="leaked"))

    names_after = {c.name for c in registry.get_channels()}
    assert "leaked" not in names_after
