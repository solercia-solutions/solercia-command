"""Delivery channel registry — the hub's extension point (design.md D1/D6).

Mutable, populated import-time by each channel's OWN domain module
(``app/email/outbox.py`` registers ``EmailChannel``, ``app/realtime/
publisher.py`` registers ``WebSocketChannel``) — precedent
``app/alerts/registry.py``, but a MUTABLE list instead of a static dict:
adding a NEW channel is ``register_channel(...)`` at import time in the
channel's own module, never an edit to this file (R1/R6, "sin tocar el
núcleo").
"""

from app.notify.ports import DeliveryChannel

_CHANNELS: list[DeliveryChannel] = []


def register_channel(channel: DeliveryChannel) -> None:
    """Register ``channel`` in the hub's fan-out list."""

    _CHANNELS.append(channel)


def get_channels() -> list[DeliveryChannel]:
    """Return a snapshot of every currently registered channel."""

    return list(_CHANNELS)
