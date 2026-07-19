"""Integrations engine — read-only hexagonal core for external providers.

Sibling of ``app/notify/``, ``app/alerts/``, ``app/email/`` and
``app/realtime/`` (design.md "Motor ``app/integrations/``"). Exposes:

- ``ports.py``: one read-only ``Protocol`` per capability + the
  ``IntegrationAdapter`` protocol every provider adapter implements.
- ``dtos.py``: provider-agnostic, frozen DTOs returned by every port.
- ``registry.py``: adapter registry populated at import time by each
  adapter's OWN module (precedent ``app/notify/registry.py``).
- ``crypto.py``: Fernet symmetric encryption for OAuth tokens at rest.
- ``state_store.py``: Redis-backed, single-use OAuth ``state`` (CSRF).
- ``oauth.py``: generic ``authorize``/``callback`` orchestration, delegating
  every provider-specific detail to the adapter.
- ``adapters/fake.py``: in-memory adapter used to validate the core's
  contract before a real provider (Microsoft 365, Google, GLPI, Jira, MCP —
  changes 15-19) exists.

Backend-only, strictly read-only in this wave (IP-R5): no port or adapter
protocol declares any operation that writes back to the provider.
"""
