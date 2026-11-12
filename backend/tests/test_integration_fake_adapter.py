"""RED tests for the in-memory `fake` adapter (IP-R3/IP-R4,
specs/integration-ports/spec.md). Registers itself at import time
(`app.integrations.adapters.fake`); no real HTTP call is ever made. The
OAuth-flow test uses `fakeredis` via the `patched_redis` conftest fixture.
"""

import pytest

from app.integrations import oauth
from app.integrations.adapters.fake import FakeAdapter
from app.integrations.dtos import (
    CalendarEvent,
    ExternalTask,
    MailMessage,
    MeetingNote,
    Ticket,
)
from app.integrations.ports import AccessContext, Capability
from app.integrations.registry import get_adapter

_CTX = AccessContext(access_token="fake-access", refresh_token=None, scopes=("mail",))


def test_fake_adapter_is_registered_at_import_time() -> None:
    """Importing the fake adapter module registers it under provider "fake"."""

    resolved = get_adapter("fake")
    assert resolved is not None
    assert isinstance(resolved, FakeAdapter)


@pytest.mark.asyncio
async def test_fake_adapter_answers_every_port_with_no_real_http_call() -> None:
    """Scenario: El fake pasa las pruebas de contrato de cada puerto — each
    of the 5 ports responds with real DTO instances, entirely in memory."""

    adapter = FakeAdapter()

    mail = await adapter.port_for(Capability.mail).list_messages(_CTX)
    calendar = await adapter.port_for(Capability.calendar).list_events(_CTX)
    tasks = await adapter.port_for(Capability.external_tasks).list_tasks(_CTX)
    notes = await adapter.port_for(Capability.meeting_notes).list_notes(_CTX)
    tickets = await adapter.port_for(Capability.tickets).list_tickets(_CTX)

    assert len(mail) == 1 and isinstance(mail[0], MailMessage)
    assert len(calendar) == 1 and isinstance(calendar[0], CalendarEvent)
    assert len(tasks) == 1 and isinstance(tasks[0], ExternalTask)
    assert len(notes) == 1 and isinstance(notes[0], MeetingNote)
    assert len(tickets) == 1 and isinstance(tickets[0], Ticket)


@pytest.mark.asyncio
async def test_authorize_then_callback_completes_the_simulated_oauth_flow(
    patched_redis,
) -> None:
    """Scenario: El fake simula el flujo OAuth completo — build_authorize
    generates a state and a provider URL; handle_callback exchanges the code
    for simulated tokens and consumes the state (IP-R3, "el núcleo delega el
    canje de tokens al adaptador")."""

    adapter = FakeAdapter()

    state, url = await oauth.build_authorize(
        adapter,
        "https://app.test/callback",
        ["mail"],
        state_payload={"connector_id": "conn-1"},
        ttl=60,
    )
    assert state in url
    assert url.startswith("https://fake.test/oauth/authorize")

    payload, tokens = await oauth.handle_callback(
        adapter, "auth-code-123", state, "https://app.test/callback"
    )
    assert payload == {"connector_id": "conn-1"}
    assert tokens.access_token == "fake-access-auth-code-123"
    assert tokens.external_account_id == "fake-account-auth-code-123"


@pytest.mark.asyncio
async def test_reused_state_is_rejected_by_the_second_callback(patched_redis) -> None:
    """Anti-replay triangulation: a second callback with the SAME state
    (already consumed) raises, proving single-use is enforced end-to-end
    through the fake adapter, not just at the state_store layer."""

    adapter = FakeAdapter()
    state, _ = await oauth.build_authorize(
        adapter,
        "https://app.test/callback",
        ["mail"],
        state_payload={"connector_id": "conn-1"},
        ttl=60,
    )
    await oauth.handle_callback(adapter, "code-1", state, "https://app.test/callback")

    with pytest.raises(oauth.StateNotFoundError):
        await oauth.handle_callback(adapter, "code-1", state, "https://app.test/callback")


def test_mail_only_adapter_is_excluded_from_the_calendar_port() -> None:
    """Scenario: Adaptador que no soporta una capacidad queda excluido de
    ese puerto — a mail-only adapter's `port_for(calendar)` is None."""

    class _MailOnlyAdapter:
        provider = "mail-only-fake"
        capabilities = frozenset({Capability.mail})

        def authorize_url(self, state, redirect_uri, scopes):
            return "https://mail-only.test/authorize"

        async def exchange_code(self, code, redirect_uri):
            raise NotImplementedError

        async def refresh(self, refresh_token):
            raise NotImplementedError

        def port_for(self, capability):
            return self if capability == Capability.mail else None

        async def list_messages(self, ctx, *, since=None, limit=50):
            return []

    adapter = _MailOnlyAdapter()
    assert adapter.port_for(Capability.mail) is adapter
    assert adapter.port_for(Capability.calendar) is None
