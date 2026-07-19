"""Provider-agnostic DTOs returned by every integration port (design.md
"Interfaces / Contracts"). Frozen dataclasses: a port response is a pure
snapshot of provider data, never an ORM row — no adapter may mutate these
after construction.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MailMessage:
    """A single email message read from a mail provider."""

    external_id: str
    subject: str
    sender: str
    recipients: tuple[str, ...]
    received_at: datetime
    snippet: str
    body_text: str | None


@dataclass(frozen=True)
class CalendarEvent:
    """A calendar event read from a calendar provider."""

    external_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    organizer: str
    attendees: tuple[str, ...]
    location: str | None


@dataclass(frozen=True)
class ExternalTask:
    """A task/issue read from an external task tracker."""

    external_id: str
    title: str
    status: str
    assignee: str | None
    due_at: datetime | None
    url: str | None


@dataclass(frozen=True)
class MeetingNote:
    """A meeting transcript/note read from a notes provider."""

    external_id: str
    meeting_title: str
    occurred_at: datetime
    transcript: str
    participants: tuple[str, ...]


@dataclass(frozen=True)
class ExternalPerson:
    """A person identity resolved from an external provider (change
    17-adapter-glpi, specs/integration-ports/spec.md IP17-R1) — e.g. GLPI's
    technician assigned to a ``Ticket``. ``email``/``document`` are optional:
    not every provider (or every person record) exposes both."""

    external_id: str
    display_name: str | None
    email: str | None
    document: str | None


@dataclass(frozen=True)
class Ticket:
    """A ticket/case read from a ticketing provider (e.g. GLPI, Jira).

    ``assignees`` (change 17-adapter-glpi, IP17-R1) defaults to an empty
    tuple — NEVER ``None`` — so every caller can iterate it unconditionally
    regardless of whether the provider populated any assigned person.
    """

    external_id: str
    key: str
    summary: str
    status: str
    priority: str | None
    requester: str | None
    created_at: datetime
    assignees: tuple[ExternalPerson, ...] = ()


@dataclass(frozen=True)
class OAuthTokens:
    """Tokens returned by an adapter's OAuth code exchange or refresh."""

    external_account_id: str
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class ExternalResource:
    """A resource published by an `external_resources` provider (change
    19-mcp-connector, specs/integration-ports/spec.md delta IP-R1) — e.g. an
    MCP server's `resources/list` entry. Provider-agnostic: never carries the
    concrete transport's own field names."""

    uri: str
    name: str
    mime_type: str | None
    description: str | None


@dataclass(frozen=True)
class ExternalTool:
    """A tool published by an `external_resources` provider (change
    19-mcp-connector, IP-R1) — e.g. an MCP server's `tools/list` entry.
    ``read_only`` mirrors the provider's own hint (MCP's `readOnlyHint`) —
    NEVER trusted alone by the adapter's `call_tool` enforcement (allowlist
    ∩ hint, mcp-connector/spec.md MC-R5); this DTO only carries the value."""

    name: str
    description: str | None
    read_only: bool
    input_schema: dict


@dataclass(frozen=True)
class ExternalResourceContent:
    """The content of a resource read or a tool call result (change
    19-mcp-connector, IP-R1). Exactly one of ``text``/``blob_b64`` is
    populated (mirrors MCP's `TextResourceContents`/`BlobResourceContents`
    union) — ``uri`` is ``None`` for a `call_tool` result (not
    URI-addressed). ``truncated`` is ``True`` only when the adapter itself
    intentionally withheld content past a configured byte tope — it is
    NEVER a partial/corrupt read silently passed through."""

    uri: str | None
    mime_type: str | None
    text: str | None
    blob_b64: str | None
    truncated: bool


@dataclass(frozen=True)
class AccountRef:
    """Identity of a connected account resolved by an ``ApiTokenHandshake``
    (change 17-adapter-glpi) — the api_token analogue of ``OAuthTokens``.

    Carries just enough to create/reactivate a ``ConnectedAccount`` row; it
    NEVER carries secret material — the raw credentials the caller already
    holds are encrypted directly into ``ConnectionCredentials`` by the
    connectors service, never round-tripped through this DTO (mirrors
    ``OAuthTokens``, which also never carries anything beyond what the
    OAuth exchange itself returns).
    """

    external_account_id: str
    display_name: str | None = None
