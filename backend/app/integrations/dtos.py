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
