"""RED tests for the integration ports' read-only boundary (IP-R5,
specs/integration-ports/spec.md "Frontera solo-lectura estricta").

Each port Protocol and the ``IntegrationAdapter`` Protocol are inspected by
their DECLARED methods (``vars(cls)``, not inherited) — a write method
(create/update/delete/reply/send toward the provider) must never appear.
Also proves the addendum contract on ``AccessContext`` (``scopes`` +
``on_tokens_refreshed`` sink) ratified by the orchestrator for change
14-integration-ports, consumed by adapters 15/16 and change 22.

``IntegrationAdapter``'s own declared-methods assertion was UPDATED by
change 17-adapter-glpi (specs/integration-ports/spec.md, MODIFIED
Requirement "Protocolo de adaptador uniforme", IP17-R2):
``authorize_url``/``exchange_code``/``refresh`` moved off
``IntegrationAdapter`` into their own ``OAuthHandshake`` Protocol so an
``api_token`` adapter (GLPI) is never forced to implement them at all —
``IntegrationAdapter`` itself now declares only ``port_for``.
"""

import dataclasses

from app.integrations.ports import (
    AccessContext,
    ApiTokenHandshake,
    CalendarReaderPort,
    ExternalTaskReaderPort,
    IntegrationAdapter,
    MailReaderPort,
    MeetingNotesReaderPort,
    OAuthHandshake,
    TicketReaderPort,
)

_READ_ONLY_PORTS = {
    MailReaderPort: {"list_messages"},
    CalendarReaderPort: {"list_events"},
    ExternalTaskReaderPort: {"list_tasks"},
    MeetingNotesReaderPort: {"list_notes"},
    TicketReaderPort: {"list_tickets"},
}

_WRITE_VERBS = ("create", "send", "reply", "update", "edit", "delete", "remove", "post_")


def _declared_methods(cls: type) -> set[str]:
    """Return the callables declared DIRECTLY on ``cls`` (not inherited)."""

    return {
        name
        for name, value in vars(cls).items()
        if not name.startswith("_") and callable(value)
    }


def test_each_port_declares_only_its_single_read_method() -> None:
    """Scenario: Ningún puerto expone escritura — each port's ONLY declared
    method is its read method; nothing named after a write verb exists."""

    for port_cls, expected_methods in _READ_ONLY_PORTS.items():
        declared = _declared_methods(port_cls)
        assert declared == expected_methods, port_cls
        for method_name in declared:
            assert not any(verb in method_name for verb in _WRITE_VERBS)


def test_integration_adapter_protocol_declares_no_write_operation() -> None:
    """Scenario: El protocolo de adaptador no declara operaciones de
    escritura — only ``port_for`` exists directly on ``IntegrationAdapter``
    since change 17 (the OAuth handshake now lives on ``OAuthHandshake``,
    the api_token handshake on ``ApiTokenHandshake``), never a write toward
    the provider."""

    declared = _declared_methods(IntegrationAdapter)
    assert declared == {"port_for"}
    for method_name in declared:
        assert not any(verb in method_name for verb in _WRITE_VERBS)


def test_oauth_handshake_protocol_declares_no_write_operation() -> None:
    """Change 17-adapter-glpi, IP17-R2: ``OAuthHandshake`` carries exactly
    the three methods extracted off ``IntegrationAdapter`` — no write verb."""

    declared = _declared_methods(OAuthHandshake)
    assert declared == {"authorize_url", "exchange_code", "refresh"}
    for method_name in declared:
        assert not any(verb in method_name for verb in _WRITE_VERBS)


def test_api_token_handshake_protocol_declares_only_connect() -> None:
    """Change 17-adapter-glpi, IP17-R2: ``ApiTokenHandshake`` declares only
    ``connect`` — no write verb (it validates credentials, it never mutates
    anything on the provider side, GA-R5)."""

    declared = _declared_methods(ApiTokenHandshake)
    assert declared == {"connect"}
    for method_name in declared:
        assert not any(verb in method_name for verb in _WRITE_VERBS)


def test_access_context_carries_scopes_and_token_refresh_sink() -> None:
    """Addendum (orchestrator-ratified): ``AccessContext`` exposes ``scopes``
    (granted scopes, for capability short-circuiting without a network call)
    and an optional ``on_tokens_refreshed`` sink the engine can pass so an
    adapter that rotates tokens mid-read hands the new tokens back — consumed
    by adapters 15/16 and change 22."""

    field_names = {f.name for f in dataclasses.fields(AccessContext)}
    assert "scopes" in field_names
    assert "on_tokens_refreshed" in field_names

    ctx = AccessContext(access_token="token-abc", refresh_token=None, scopes=("mail",))
    assert ctx.scopes == ("mail",)
    assert ctx.on_tokens_refreshed is None
