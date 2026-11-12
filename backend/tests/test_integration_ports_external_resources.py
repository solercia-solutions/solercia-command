"""RED tests for the core's read-only `external_resources` port (change
19-mcp-connector, Lote 2, specs/integration-ports/spec.md delta — IP-R1,
IP-R2, IP-R3).

Structural/contract tests only — no I/O, no adapter implementation (the real
`mcp` adapter is Lote 5). Mirrors `test_integration_ports_contract.py`'s
"inspect declared methods" style, extended to prove:

- IP-R1: `ExternalResourceReaderPort` declares exactly
  `list_resources`/`read_resource`/`list_tools`/`call_tool` — no OTHER write
  verb — and DTOs (`ExternalResource`/`ExternalTool`/`ExternalResourceContent`)
  are frozen, provider-agnostic dataclasses.
- IP-R2: `CredentialKind` gains `none` WITHOUT redefining `oauth`/`api_token`
  (change 17-adapter-glpi stays the sole owner of those two); an adapter
  declaring direct credential acquisition (e.g. a future `mcp`-shaped one)
  is rejected by the core's OAuth orchestration (`app/integrations/oauth.py`)
  BEFORE any `state` is touched — same defense `test_connectors_api_token.py`
  already proves for GLPI, now proven generically at the core level for ANY
  non-oauth adapter shape.
- IP-R3: `IntegrationAdapter` gains `credential_kinds: frozenset[CredentialKind]`
  (a NEW field, additive — `test_integration_adapter_protocol_declares_no_write_
  operation` in `test_integration_ports_contract.py` keeps passing unchanged
  since a `Protocol` field annotation without a default is never a declared
  CALLABLE). `call_tool`'s read-only enforcement is a RUNTIME property of the
  adapter, not something a `Protocol` can structurally enforce — proven live
  against the fake MCP server in Lote 4/6, not here.
"""

import dataclasses
from typing import get_type_hints

import pytest

from app.integrations import oauth, state_store
from app.integrations.dtos import ExternalResource, ExternalResourceContent, ExternalTool
from app.integrations.ports import (
    Capability,
    CredentialKind,
    ExternalResourceReaderPort,
    IntegrationAdapter,
)

_WRITE_VERBS = ("create", "send", "reply", "update", "edit", "delete", "remove", "post_")


def _declared_methods(cls: type) -> set[str]:
    return {
        name
        for name, value in vars(cls).items()
        if not name.startswith("_") and callable(value)
    }


class _DirectAcquisitionAdapter:
    """Minimal fake adapter shaped like a direct-credential-acquisition
    provider (e.g. `mcp`) — `oauth=None`, never touches `state_store`."""

    provider = "fake-direct"
    capabilities = frozenset({Capability.external_resources})
    credential_kind = CredentialKind.api_token
    credential_kinds = frozenset({CredentialKind.api_token, CredentialKind.none})
    oauth = None
    api_token = None

    def port_for(self, capability: Capability) -> object | None:
        return None


# ---------------------------------------------------------------------------
# IP-R1 — puerto de solo lectura de recursos externos
# ---------------------------------------------------------------------------


def test_external_resource_reader_port_declares_only_read_and_gated_call() -> None:
    """Scenario: El puerto expone descubrimiento y lectura sin credenciales
    de escritura — declared methods are exactly the four read/gated ops,
    none of them named after a generic write verb."""

    declared = _declared_methods(ExternalResourceReaderPort)
    assert declared == {"list_resources", "read_resource", "list_tools", "call_tool"}
    for method_name in declared:
        assert not any(verb in method_name for verb in _WRITE_VERBS)


def test_external_resource_dtos_are_frozen_and_provider_agnostic() -> None:
    """DTOs returned by the port are frozen dataclasses — a snapshot, never
    a live handle back into the provider or an ORM row."""

    for dto_cls in (ExternalResource, ExternalTool, ExternalResourceContent):
        assert dataclasses.is_dataclass(dto_cls)
        params = dto_cls.__dataclass_params__
        assert params.frozen is True

    resource = ExternalResource(
        uri="mcp://server/notes/1",
        name="Nota de prueba",
        mime_type="text/plain",
        description=None,
    )
    assert resource.uri == "mcp://server/notes/1"

    tool = ExternalTool(
        name="lookup",
        description="Busca un registro.",
        read_only=True,
        input_schema={"type": "object"},
    )
    assert tool.read_only is True

    content = ExternalResourceContent(
        uri="mcp://server/notes/1",
        mime_type="text/plain",
        text="contenido",
        blob_b64=None,
        truncated=False,
    )
    assert content.truncated is False


# ---------------------------------------------------------------------------
# IP-R2 — protocolo de adaptador uniforme (adquisición directa)
# ---------------------------------------------------------------------------


def test_credential_kind_gains_none_without_redefining_existing_values() -> None:
    """Scenario: `CredentialKind` admite `none` sumado al conjunto
    (`oauth`, `api_token`) del cambio 17-adapter-glpi — sin redefinirlos."""

    assert CredentialKind.oauth == "oauth"
    assert CredentialKind.api_token == "api_token"
    assert CredentialKind.none == "none"
    assert {member.value for member in CredentialKind} == {"oauth", "api_token", "none"}


@pytest.mark.asyncio(loop_scope="session")
async def test_direct_acquisition_adapter_omits_authorize_callback_before_any_state(
    patched_redis,
) -> None:
    """Scenario: Adaptador con adquisición directa de credencial omite
    authorize/callback — the core rejects the OAuth handshake for ANY
    non-oauth adapter shape (not just GLPI) BEFORE `state_store.put` is ever
    reached."""

    adapter = _DirectAcquisitionAdapter()
    before = await patched_redis.dbsize()

    with pytest.raises(oauth.CredentialKindMismatchError):
        await oauth.build_authorize(
            adapter,
            "https://app.test/callback",
            [],
            state_payload={"connector_id": "x"},
            ttl=60,
        )

    after = await patched_redis.dbsize()
    assert after == before

    with pytest.raises(oauth.CredentialKindMismatchError):
        await oauth.handle_callback(adapter, "code-x", "state-x", "https://app.test/callback")


def test_direct_acquisition_adapter_state_store_is_never_touched(monkeypatch) -> None:
    """Defense-in-depth companion to the scenario above: patches
    `state_store.put` itself to prove it is NEVER CALLED for a direct
    adapter, regardless of Redis's own bookkeeping."""

    calls: list[object] = []
    monkeypatch.setattr(state_store, "put", lambda *a, **kw: calls.append((a, kw)))

    adapter = _DirectAcquisitionAdapter()

    with pytest.raises(oauth.CredentialKindMismatchError):
        import asyncio

        asyncio.run(
            oauth.build_authorize(
                adapter,
                "https://app.test/callback",
                [],
                state_payload={"connector_id": "x"},
                ttl=60,
            )
        )

    assert calls == []


# ---------------------------------------------------------------------------
# IP-R3 — IntegrationAdapter.credential_kinds (delta aditivo)
# ---------------------------------------------------------------------------


def test_integration_adapter_declares_credential_kinds_frozenset_field() -> None:
    """`IntegrationAdapter` gains `credential_kinds: frozenset[CredentialKind]`
    — additive: `port_for` stays the ONLY declared CALLABLE (a `Protocol`
    field annotation is never a method), so
    `test_integration_ports_contract.py`'s existing assertion
    (`declared == {"port_for"}`) is untouched by this delta."""

    hints = get_type_hints(IntegrationAdapter)
    assert "credential_kinds" in hints
    assert hints["credential_kinds"] == frozenset[CredentialKind]

    declared_callables = {
        name
        for name, value in vars(IntegrationAdapter).items()
        if not name.startswith("_") and callable(value)
    }
    assert declared_callables == {"port_for"}


def test_direct_acquisition_adapter_declares_both_kinds_it_supports() -> None:
    """A single-`credential_kind` adapter (GLPI/Jira: always `api_token`;
    fake/Google/M365: always `oauth`) cannot express "this adapter accepts
    EITHER `api_token` OR `none` depending on the connector being
    registered" — `credential_kinds` is the set-valued field that does."""

    adapter = _DirectAcquisitionAdapter()
    assert adapter.credential_kinds == frozenset({CredentialKind.api_token, CredentialKind.none})
