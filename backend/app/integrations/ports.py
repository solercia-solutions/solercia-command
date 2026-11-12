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

``ExternalResourceReaderPort``/``Capability.external_resources``/
``CredentialKind.none``/``IntegrationAdapter.credential_kinds`` (change
19-mcp-connector, specs/integration-ports/spec.md delta, IP-R1/IP-R2/IP-R3)
extend the SAME discipline one more axis: a provider whose ONLY sensible
shape is "list/read/discover, plus one gated invoke" (MCP) gets its own
disjoint port instead of overloading an existing one. ``credential_kinds``
is additive to (never replaces) the existing singular ``credential_kind`` —
every PRE-19 adapter (fake/M365/Google: always ``oauth``; GLPI/Jira: always
``api_token``) keeps a FIXED kind; ``mcp`` is the first adapter whose
connectors may be EITHER ``api_token`` OR ``none`` depending on how the
admin registers the server, which a single-valued field cannot express.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from app.integrations.dtos import (
    AccountRef,
    CalendarEvent,
    ExternalResource,
    ExternalResourceContent,
    ExternalTask,
    ExternalTool,
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
    # Change 19-mcp-connector, IP-R1 — read-only discovery over a generic
    # external resource/tool provider (MCP servers, first consumer).
    external_resources = "external_resources"


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


class ExternalResourceReaderPort(Protocol):
    """Read-only discovery + gated invocation over a generic external
    resource/tool provider (change 19-mcp-connector, IP-R1 — first
    consumer: MCP servers).

    ``call_tool`` is the ONE narrow exception to "solo lectura" the core
    tolerates in this wave (specs/integration-ports/spec.md delta, MODIFIED
    Requirement "Frontera solo-lectura estricta"): it is NEVER safe by
    itself — an adapter MAY declare it only when it also applies
    default-deny + the provider's own ``readOnlyHint`` + an explicit
    per-connector allowlist (mcp-connector/spec.md MC-R5). This Protocol
    cannot enforce that at the type level (Python `Protocol`s are
    structural, not runtime-checked here) — the enforcement itself is
    proven live against the fake MCP server (Lote 4's
    `test_mcp_adapter_reader.py`) and the REST layer (Lote 6's
    `test_connectors_mcp_reader.py`), never merely assumed from this
    signature existing.
    """

    async def list_resources(self, ctx: AccessContext) -> list[ExternalResource]: ...

    async def read_resource(self, ctx: AccessContext, uri: str) -> ExternalResourceContent: ...

    async def list_tools(self, ctx: AccessContext) -> list[ExternalTool]: ...

    async def call_tool(
        self, ctx: AccessContext, name: str, arguments: dict[str, Any]
    ) -> ExternalResourceContent: ...


class CredentialKind(StrEnum):
    """How a connector's credentials are obtained (change 17-adapter-glpi).

    ``oauth`` — delegated browser handshake (authorize/callback), the ONLY
    kind change 14 originally modeled. ``api_token`` — direct credential
    registration (GLPI's App-Token + user_token, validated via
    ``initSession``), no browser redirection, no ``state``. ``none``
    (change 19-mcp-connector, specs/connectors/spec.md delta C-R1) — the
    external server requires NO credential at all (e.g. a public MCP
    server); adding this value NEVER redefines ``oauth``/``api_token``,
    which change 17-adapter-glpi keeps sole ownership of.
    """

    oauth = "oauth"
    api_token = "api_token"
    none = "none"


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

    ``credential_kinds`` (change 19-mcp-connector, IP-R3) is ADDITIVE, never
    a replacement: every pre-19 adapter has a FIXED ``credential_kind``
    (fake/M365/Google: ``oauth``; GLPI/Jira: ``api_token``), so
    ``credential_kinds`` for those is just ``frozenset({credential_kind})``.
    ``mcp`` is the first adapter whose CONNECTORS may be registered as
    EITHER ``api_token`` OR ``none`` (an admin's per-server choice) — a
    single scalar field cannot express "this adapter accepts either of
    these two", so ``credential_kinds`` is the set the connectors service
    validates a registration request's chosen ``credential_kind`` against.
    """

    provider: str
    capabilities: frozenset[Capability]
    credential_kind: CredentialKind
    credential_kinds: frozenset[CredentialKind]
    oauth: OAuthHandshake | None
    api_token: ApiTokenHandshake | None

    def port_for(self, capability: Capability) -> object | None:
        """Return this adapter's implementation of ``capability``'s port,
        or ``None`` when the adapter does not support it."""
        ...
