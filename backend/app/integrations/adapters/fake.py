"""In-memory ``fake`` adapter — no real HTTP calls, self-registers at
import time (design.md, precedent ``app/email/outbox.py``). Implements all
five read ports with canned sample data plus a simulated OAuth handshake, so
the core's contract can be exercised end-to-end before a real provider
adapter exists (IP-R4, "adaptador fake en memoria para pruebas de
contrato").
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from app.integrations.dtos import (
    CalendarEvent,
    ExternalTask,
    MailMessage,
    MeetingNote,
    OAuthTokens,
    Ticket,
)
from app.integrations.ports import (
    AccessContext,
    ApiTokenHandshake,
    Capability,
    CredentialKind,
    OAuthHandshake,
)
from app.integrations.registry import register_adapter


class _FakeMailPort:
    async def list_messages(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[MailMessage]:
        return [
            MailMessage(
                external_id="fake-mail-1",
                subject="Mensaje de prueba",
                sender="remitente@fake.test",
                recipients=("destinatario@fake.test",),
                received_at=datetime.now(UTC),
                snippet="Vista previa de prueba.",
                body_text="Cuerpo completo de prueba.",
            )
        ][:limit]


class _FakeCalendarPort:
    async def list_events(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[CalendarEvent]:
        return [
            CalendarEvent(
                external_id="fake-event-1",
                title="Evento de prueba",
                starts_at=datetime.now(UTC),
                ends_at=datetime.now(UTC),
                organizer="organizador@fake.test",
                attendees=("asistente@fake.test",),
                location="Sala virtual",
            )
        ][:limit]


class _FakeExternalTaskPort:
    async def list_tasks(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[ExternalTask]:
        return [
            ExternalTask(
                external_id="fake-task-1",
                title="Tarea externa de prueba",
                status="open",
                assignee="asignado@fake.test",
                due_at=None,
                url="https://fake.test/tasks/1",
            )
        ][:limit]


class _FakeMeetingNotesPort:
    async def list_notes(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[MeetingNote]:
        return [
            MeetingNote(
                external_id="fake-note-1",
                meeting_title="Reunión de prueba",
                occurred_at=datetime.now(UTC),
                transcript="Transcripción de prueba.",
                participants=("participante@fake.test",),
            )
        ][:limit]


class _FakeTicketPort:
    async def list_tickets(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[Ticket]:
        return [
            Ticket(
                external_id="fake-ticket-1",
                key="FAKE-1",
                summary="Ticket de prueba",
                status="open",
                priority="medium",
                requester="solicitante@fake.test",
                created_at=datetime.now(UTC),
            )
        ][:limit]


class FakeAdapter:
    """In-memory adapter used to validate the core's contract (IP-R4)."""

    provider = "fake"
    capabilities = frozenset(
        {
            Capability.mail,
            Capability.calendar,
            Capability.external_tasks,
            Capability.meeting_notes,
            Capability.tickets,
        }
    )
    credential_kind = CredentialKind.oauth
    # Change 19-mcp-connector, IP-R3 — additive, mirrors `credential_kind`
    # for every adapter that (unlike `mcp`) only ever registers ONE kind.
    credential_kinds = frozenset({CredentialKind.oauth})

    def __init__(self) -> None:
        self._ports: dict[Capability, object] = {
            Capability.mail: _FakeMailPort(),
            Capability.calendar: _FakeCalendarPort(),
            Capability.external_tasks: _FakeExternalTaskPort(),
            Capability.meeting_notes: _FakeMeetingNotesPort(),
            Capability.tickets: _FakeTicketPort(),
        }
        # OAuth handshake methods live directly on `self` (unchanged since
        # before change 17) — `self.oauth = self` just exposes them through
        # the new `IntegrationAdapter.oauth` slot the core now reads
        # (`app/integrations/oauth.py`, IP17-R2). `api_token` stays `None`:
        # `fake` is (and stays) an `oauth`-kind adapter.
        self.oauth: OAuthHandshake | None = self
        self.api_token: ApiTokenHandshake | None = None

    def authorize_url(self, state: str, redirect_uri: str, scopes: Sequence[str]) -> str:
        """Build a fake authorize URL — no real network call."""

        scope_param = "+".join(scopes)
        return (
            f"https://fake.test/oauth/authorize?state={state}"
            f"&redirect_uri={redirect_uri}&scope={scope_param}"
        )

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        """Simulate a code-for-tokens exchange without any real HTTP call."""

        return OAuthTokens(
            external_account_id=f"fake-account-{code}",
            access_token=f"fake-access-{code}",
            refresh_token=f"fake-refresh-{code}",
            expires_at=None,
            scopes=("mail",),
        )

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        """Simulate a refresh-token exchange without any real HTTP call."""

        return OAuthTokens(
            external_account_id="fake-account-refreshed",
            access_token=f"fake-access-refreshed-{refresh_token}",
            refresh_token=refresh_token,
            expires_at=None,
            scopes=("mail",),
        )

    def port_for(self, capability: Capability) -> object | None:
        """Return the port implementation for ``capability``, or ``None``."""

        if capability not in self.capabilities:
            return None
        return self._ports.get(capability)


# Registered at import time (IP-R2, "sin tocar el núcleo"): this module
# registers ITSELF, the core never imports it directly.
register_adapter(FakeAdapter())
