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

``CredentialKind``/``OAuthHandshake``/``ApiTokenHandshake`` (change
17-adapter-glpi, specs/integration-ports/spec.md IP17-R2 — MODIFIED
Requirement "Protocolo de adaptador uniforme") extend this same
"one-Protocol-per-responsibility" discipline to the credential/handshake
axis: an adapter's OAuth methods moved out of ``IntegrationAdapter`` itself
into a dedicated ``OAuthHandshake`` Protocol so an ``api_token`` adapter
(GLPI) is never forced to half-implement ``authorize_url``/``exchange_code``
with a dummy/``NotImplementedError`` body — the exact "mega-Protocol con
ramas None" anti-pattern design.md's Rejected Alternatives already ruled
out for capabilities, now ruled out for handshakes too.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from app.integrations.dtos import (
    AccountRef,
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


class CredentialKind(StrEnum):
    """How a connector's credentials are obtained (change 17-adapter-glpi).

    ``oauth`` — delegated browser handshake (authorize/callback), the ONLY
    kind change 14 originally modeled. ``api_token`` — direct credential
    registration (GLPI's App-Token + user_token, validated via
    ``initSession``), no browser redirection, no ``state``.
    """

    oauth = "oauth"
    api_token = "api_token"


class OAuthHandshake(Protocol):
    """Delegated OAuth token exchange — extracted VERBATIM from the
    original ``IntegrationAdapter`` (change 14) into its own Protocol
    (change 17) so an adapter that never does a browser handshake is never
    forced to declare these methods at all."""

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


class ApiTokenHandshake(Protocol):
    """Direct credential registration handshake (change 17-adapter-glpi) —
    GLPI-style App-Token + user_token, validated by calling the provider's
    own session init/kill cycle. No ``state``, no browser redirection."""

    async def connect(self, raw: Mapping[str, str]) -> AccountRef:
        """Validate ``raw`` provider credentials and return the
        :class:`AccountRef` identifying the connected account.

        Implementations validate by round-tripping the provider's own
        session lifecycle (e.g. GLPI's ``initSession``/``killSession``) —
        never by persisting anything themselves; persistence stays the
        connectors service's job (mirrors ``OAuthHandshake.exchange_code``,
        which likewise only returns tokens, never persists them).
        """
        ...


class IntegrationAdapter(Protocol):
    """Common shape every registered provider adapter MUST implement.

    ``credential_kind`` tells the core which of ``oauth``/``api_token`` is
    populated (the OTHER stays ``None``) — the core (``app/integrations/
    oauth.py``, ``app/modules/connectors/service.py``) always checks
    ``credential_kind`` FIRST and only then touches the matching attribute,
    so an adapter never needs to half-implement the handshake it does not
    support (IP17-R2).
    """

    provider: str
    capabilities: frozenset[Capability]
    credential_kind: CredentialKind
    oauth: OAuthHandshake | None
    api_token: ApiTokenHandshake | None

    def port_for(self, capability: Capability) -> object | None:
        """Return this adapter's implementation of ``capability``'s port,
        or ``None`` when the adapter does not support it."""
        ...
