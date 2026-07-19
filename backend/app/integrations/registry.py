"""Adapter registry — the integrations core's extension point (design.md,
mirrors ``app/notify/registry.py``). A dict keyed by ``provider`` (not the
notify hub's fan-out list, since adapters are looked up by name, never
broadcast to all). Adding a new adapter is ``register_adapter(...)`` at
import time in the adapter's OWN module — never an edit to this file
(IP-R2, "sin tocar el núcleo").
"""

from app.integrations.ports import IntegrationAdapter

_ADAPTERS: dict[str, IntegrationAdapter] = {}


def register_adapter(adapter: IntegrationAdapter) -> None:
    """Register ``adapter`` under its own ``provider`` key."""

    _ADAPTERS[adapter.provider] = adapter


def get_adapter(provider: str) -> IntegrationAdapter | None:
    """Return the adapter registered for ``provider``, or ``None``."""

    return _ADAPTERS.get(provider)
