"""RED tests for the 17-adapter-glpi delta on the 14-integration-ports core
(specs/17-adapter-glpi/specs/integration-ports/spec.md, IP17-R1/IP17-R2).

Two independent deltas, both exercised here without any HTTP/DB access:

- ``Ticket.assignees``/``ExternalPerson`` (IP17-R1) — the ticket DTO gains a
  read-only collection of assigned-person identities, defaulting to an empty
  tuple, never ``None``.
- ``CredentialKind``/``ApiTokenHandshake`` (IP17-R2) — an adapter registered
  with ``credential_kind=api_token`` never participates in the core's
  ``authorize``/``callback`` OAuth orchestration; the core rejects the
  operation with a controlled error, BEFORE any ``state`` is generated or
  consumed (mirrors ``test_integration_fake_adapter.py``'s use of
  ``patched_redis`` for the real ``oauth.py``/``state_store.py`` core).
"""

import dataclasses
from datetime import UTC, datetime

import pytest

from app.integrations import oauth, state_store
from app.integrations.dtos import ExternalPerson, Ticket
from app.integrations.ports import ApiTokenHandshake, CredentialKind


def _ticket(**overrides: object) -> Ticket:
    defaults: dict[str, object] = {
        "external_id": "t-1",
        "key": "T-1",
        "summary": "Resumen del caso",
        "status": "open",
        "priority": None,
        "requester": None,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return Ticket(**defaults)  # type: ignore[arg-type]


class TestExternalPersonAndAssignees:
    """IP17-R1: identidad de personas asignadas en el puerto de tickets."""

    def test_ticket_assignees_defaults_to_empty_tuple_never_none(self) -> None:
        """Scenario: Ticket sin asignado expone lista vacía."""

        ticket = _ticket()
        assert ticket.assignees == ()
        assert ticket.assignees is not None

    def test_ticket_assignees_holds_full_external_person_identity(self) -> None:
        """Scenario: Ticket con asignado incluye su identidad completa."""

        person = ExternalPerson(
            external_id="42",
            display_name="Ana Torres",
            email="ana.torres@example.com",
            document="123456789",
        )
        ticket = _ticket(assignees=(person,))

        assert ticket.assignees == (person,)
        assert ticket.assignees[0].display_name == "Ana Torres"
        assert ticket.assignees[0].email == "ana.torres@example.com"

    def test_external_person_is_a_frozen_dataclass(self) -> None:
        person = ExternalPerson(
            external_id="42", display_name="Ana Torres", email=None, document=None
        )
        assert dataclasses.is_dataclass(person)
        with pytest.raises(dataclasses.FrozenInstanceError):
            person.display_name = "Otro Nombre"  # type: ignore[misc]


class TestCredentialKind:
    """IP17-R2: `credential_kind` distingue `oauth` de `api_token`."""

    def test_exposes_oauth_and_api_token_members(self) -> None:
        assert CredentialKind.oauth == "oauth"
        assert CredentialKind.api_token == "api_token"


class _StubApiTokenHandshake:
    """Minimal `ApiTokenHandshake` — validates without any real HTTP call."""

    async def connect(self, raw: dict) -> None:  # pragma: no cover - unused here
        return None


class _ApiTokenOnlyAdapter:
    """Test double: an adapter registered with `credential_kind=api_token`
    that NEVER implements the OAuth handshake (IP17-R2, "sin OAuthHandshake")
    — no `authorize_url`/`exchange_code`/`refresh`, ``oauth`` stays ``None``.
    """

    provider = "test-api-token-only"
    capabilities: frozenset = frozenset()
    credential_kind = CredentialKind.api_token
    oauth = None

    def __init__(self) -> None:
        self.api_token: ApiTokenHandshake = _StubApiTokenHandshake()

    def port_for(self, capability: object) -> object | None:
        return None


class TestApiTokenAdapterRejectedByOAuthCore:
    """IP17-R2, scenario "Adaptador `api_token` no participa del flujo OAuth"."""

    @pytest.mark.asyncio
    async def test_build_authorize_rejects_without_generating_any_state(
        self, patched_redis, monkeypatch
    ) -> None:
        async def _fail_if_called(*args: object, **kwargs: object) -> None:
            raise AssertionError(
                "state_store.put NUNCA debe invocarse para un adaptador "
                "api_token: el rechazo debe ocurrir ANTES de generar state."
            )

        monkeypatch.setattr(state_store, "put", _fail_if_called)

        adapter = _ApiTokenOnlyAdapter()
        with pytest.raises(oauth.CredentialKindMismatchError):
            await oauth.build_authorize(
                adapter,
                "https://app.test/callback",
                [],
                state_payload={"connector_id": "conn-1"},
                ttl=60,
            )

    @pytest.mark.asyncio
    async def test_handle_callback_rejects_an_api_token_adapter(
        self, patched_redis, monkeypatch
    ) -> None:
        async def _fail_if_called(*args: object, **kwargs: object) -> None:
            raise AssertionError(
                "state_store.pop NUNCA debe invocarse para un adaptador "
                "api_token: el rechazo debe ocurrir ANTES de tocar el state."
            )

        monkeypatch.setattr(state_store, "pop", _fail_if_called)

        adapter = _ApiTokenOnlyAdapter()
        with pytest.raises(oauth.CredentialKindMismatchError):
            await oauth.handle_callback(
                adapter, "code-1", "any-state", "https://app.test/callback"
            )
