"""Read-only ports — one ``Protocol`` per capability (design.md "Un Protocol
por capacidad + adaptador declara lo que soporta"). Each port is DISJOINT: a
provider that only supports "mail" simply never implements the other
protocols, instead of implementing a mega-Protocol with ``None``-branches
(Rejected Alternatives) — a half-implemented capability never compiles as a
declared port.

``AccessContext`` is the decrypted, provider-agnostic handle every port
method receives — it carries the caller's access token, the account's
granted ``scopes`` (so an adapter/caller can skip a network call for a
capability that was never granted) and an optional ``on_tokens_refreshed``
sink the engine may pass so an adapter that silently refreshes tokens
mid-read can hand the new ``OAuthTokens`` back without knowing anything
about persistence — this addendum is consumed by adapters 15/16 and change
22 (orchestrator-ratified, aditivo to the original design.md contract).
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from app.integrations.dtos import (
    CalendarEvent,
    ExternalTask,
    MailMessage,
    MeetingNote,
    OAuthTokens,
    Ticket,
)


class Capability(StrEnum):
    """A capability an adapter may support, one port per value."""

    mail = "mail"
    calendar = "calendar"
    external_tasks = "external_tasks"
    meeting_notes = "meeting_notes"
    tickets = "tickets"


@dataclass(frozen=True)
class AccessContext:
    """Decrypted access handle passed into every port's read methods."""

    access_token: str
    refresh_token: str | None
    scopes: tuple[str, ...]
    on_tokens_refreshed: Callable[[OAuthTokens], Awaitable[None]] | None = None


class MailReaderPort(Protocol):
    """Read-only access to a mail provider's messages."""

    async def list_messages(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[MailMessage]: ...


class CalendarReaderPort(Protocol):
    """Read-only access to a calendar provider's events."""

    async def list_events(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[CalendarEvent]: ...


class ExternalTaskReaderPort(Protocol):
    """Read-only access to an external task tracker's items."""

    async def list_tasks(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[ExternalTask]: ...


class MeetingNotesReaderPort(Protocol):
    """Read-only access to a meeting notes/transcripts provider."""

    async def list_notes(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[MeetingNote]: ...


class TicketReaderPort(Protocol):
    """Read-only access to a ticketing/case provider."""

    async def list_tickets(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[Ticket]: ...


class IntegrationAdapter(Protocol):
    """Common shape every registered provider adapter MUST implement."""

    provider: str
    capabilities: frozenset[Capability]

    def authorize_url(
        self, state: str, redirect_uri: str, scopes: Sequence[str]
    ) -> str:
        """Build the provider's authorization URL for the OAuth handshake."""
        ...

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        """Exchange an authorization ``code`` for tokens."""
        ...

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        """Exchange a ``refresh_token`` for a fresh set of tokens.

        Signature ready for renewal-on-expiry; the orchestration that calls
        this (refresh-on-read) is deferred to the read-side waves (15-19/22,
        design.md Open Questions).
        """
        ...

    def port_for(self, capability: Capability) -> object | None:
        """Return this adapter's implementation of ``capability``'s port,
        or ``None`` when the adapter does not support it."""
        ...
