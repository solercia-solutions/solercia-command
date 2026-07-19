"""Connectors module — CRUD + OAuth flow REST API (change 14-integration-ports).

Router → service → repository, same pattern as ``app/modules/assets``. Sits
on top of the ``app/integrations/`` engine (registry, OAuth handshake,
crypto, state store) without knowing any provider-specific detail.
"""
