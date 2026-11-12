"""Read-only port implementations over Microsoft Graph (change
15-adapter-microsoft365, design.md). Each class implements ONE of the 14's
port ``Protocol``s (``MailReaderPort``/``CalendarReaderPort``/
``ExternalTaskReaderPort``/``MeetingNotesReaderPort``) against a Graph
endpoint, via the shared :class:`GraphClient` (pagination + TLS/anti-SSRF +
401/429 resilience) and ``mappers.py`` (Graph JSON → DTO).

``_GraphPortBase`` centralizes the TWO pieces every port repeats: building a
:class:`GraphClient` wired with ``oauth.refresh`` as the 401 recovery
callable, AND the ``since``-filter + truncate-to-``bounded_limit``
client-side pass every endpoint without a server-side date filter (Planner
tasks, meeting transcripts) needs — every subclass only adds its endpoint
path, query and mapper.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.microsoft365 import errors, oauth
from app.integrations.adapters.microsoft365.client import GraphClient
from app.integrations.adapters.microsoft365.mappers import (
    graph_datetime,
    map_calendar_event,
    map_external_task,
    map_mail_message,
    map_meeting_note,
)
from app.integrations.dtos import (
    CalendarEvent,
    ExternalTask,
    MailMessage,
    MeetingNote,
    OAuthTokens,
)
from app.integrations.ports import AccessContext
from app.shared.exceptions import AppException

# Graph's own per-request `$top` ceiling used by `_page_size` below — a port
# never asks for more items per page than this, regardless of `limit`.
GRAPH_PAGE_CAP = 50


def _iso_z(value: datetime) -> str:
    """Format ``value`` as the UTC ``...Z`` timestamp Graph's ``$filter``
    expects."""

    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class _GraphPortBase:
    """Shared plumbing for every Graph-backed read port."""

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def _bounded_limit(self, limit: int) -> int:
        return max(0, min(limit, self._settings.M365_MAX_LIMIT))

    def _page_size(self, limit: int) -> int:
        return min(self._bounded_limit(limit), GRAPH_PAGE_CAP) or 1

    def _refresh(self) -> Callable[[str], Any]:
        async def _call(refresh_token: str) -> OAuthTokens:
            return await oauth.refresh(
                refresh_token, settings=self._settings, transport=self._transport
            )

        return _call

    def _client(self, ctx: AccessContext) -> GraphClient:
        return GraphClient(
            ctx,
            transport=self._transport,
            settings=self._settings,
            refresh=self._refresh(),
        )

    def _since_or_default(self, since: datetime | None) -> datetime:
        if since is not None:
            return since
        return datetime.now(UTC) - timedelta(days=self._settings.M365_DEFAULT_SINCE_DAYS)

    def _filtered_since_and_truncated(
        self,
        raw_items: list[dict[str, Any]],
        *,
        since: datetime,
        bounded_limit: int,
    ) -> list[dict[str, Any]]:
        """Filter ``raw_items`` by ``createdDateTime >= since`` and
        truncate to ``bounded_limit`` — the ONE client-side pass
        ``list_tasks``/``list_notes`` both need."""

        recent = [
            raw for raw in raw_items if graph_datetime(raw["createdDateTime"]) >= since
        ]
        return recent[:bounded_limit]


class GraphMailReader(_GraphPortBase):
    """``MailReaderPort`` over Microsoft Graph's ``/me/messages`` (scope
    ``Mail.Read``)."""

    async def list_messages(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[MailMessage]:
        bounded_limit = self._bounded_limit(limit)
        url = self._build_url(since, bounded_limit)
        client = self._client(ctx)
        raw_items = await client.paginate(url, limit=bounded_limit)
        return [map_mail_message(item) for item in raw_items]

    def _build_url(self, since: datetime | None, bounded_limit: int) -> str:
        effective_since = self._since_or_default(since)
        query = {
            "$select": "id,subject,bodyPreview,receivedDateTime,from,toRecipients,body",
            "$top": str(self._page_size(bounded_limit)),
            "$filter": f"receivedDateTime ge {_iso_z(effective_since)}",
            "$orderby": "receivedDateTime desc",
        }
        return f"/me/messages?{urlencode(query)}"


class GraphCalendarReader(_GraphPortBase):
    """``CalendarReaderPort`` over Microsoft Graph's ``/me/calendarView``
    (scope ``Calendars.Read``)."""

    async def list_events(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[CalendarEvent]:
        bounded_limit = self._bounded_limit(limit)
        url = self._build_url(since, bounded_limit)
        client = self._client(ctx)
        raw_items = await client.paginate(url, limit=bounded_limit)
        return [map_calendar_event(item) for item in raw_items]

    def _build_url(self, since: datetime | None, bounded_limit: int) -> str:
        start = self._since_or_default(since)
        end = datetime.now(UTC) + timedelta(
            days=self._settings.M365_CALENDAR_FUTURE_DAYS
        )
        query = {
            "$select": "id,subject,start,end,organizer,attendees,location",
            "$top": str(self._page_size(bounded_limit)),
            "$orderby": "start/dateTime",
            "startDateTime": _iso_z(start),
            "endDateTime": _iso_z(end),
        }
        return f"/me/calendarView?{urlencode(query)}"


class GraphExternalTaskReader(_GraphPortBase):
    """``ExternalTaskReaderPort`` over Microsoft Graph's
    ``/me/planner/tasks`` ONLY (scope ``Tasks.Read``) — Microsoft To Do is
    explicitly OUT of scope for this wave (spec.md, "sin Microsoft To
    Do").

    Graph's Planner endpoint accepts no server-side date filter, so
    ``since``/``limit`` are applied CLIENT-side, by ``createdDateTime``,
    AFTER every page is fetched (spec.md, "filtro client-side")."""

    async def list_tasks(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[ExternalTask]:
        bounded_limit = self._bounded_limit(limit)
        effective_since = self._since_or_default(since)
        client = self._client(ctx)

        try:
            raw_items = await client.paginate(
                "/me/planner/tasks", limit=self._settings.M365_MAX_LIMIT
            )
        except AppException as exc:
            if exc.code == "capability_unavailable":
                # Tenant sin Planner/Grupos M365 — Graph responde 403; el
                # spec exige degradar a lista vacía, NUNCA error.
                return []
            raise

        recent = self._filtered_since_and_truncated(
            raw_items, since=effective_since, bounded_limit=bounded_limit
        )
        return [map_external_task(raw) for raw in recent]


_MEETING_NOTES_SCOPE = "OnlineMeetingTranscript.Read.All"


class GraphMeetingNotesReader(_GraphPortBase):
    """``MeetingNotesReaderPort`` over Microsoft Graph's
    ``/me/onlineMeetings/getAllTranscripts`` (+ each transcript's
    ``.../content``), scopes ``OnlineMeetingTranscript.Read.All`` +
    ``OnlineMeetings.Read``.

    Degrades to :func:`errors.capability_unavailable` WITHOUT any network
    call when the connected account's granted scopes (``ctx.scopes``,
    persisted by the 14) don't include the transcript scope — admin
    consent for a ``.All`` delegated permission is opt-in per connector
    (design.md ADR #1), commonly absent. The SAME degradation applies when
    Graph itself answers ``403 Authorization_RequestDenied`` at runtime
    (``GraphClient`` maps every ``403`` this way — defense in depth: a
    token's claimed scopes and its live grant can drift, e.g. revoked
    admin consent) — neither path ever affects the adapter's other ports.
    """

    async def list_notes(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[MeetingNote]:
        if _MEETING_NOTES_SCOPE not in ctx.scopes:
            raise errors.capability_unavailable()

        bounded_limit = self._bounded_limit(limit)
        effective_since = self._since_or_default(since)
        client = self._client(ctx)

        raw_transcripts = await client.paginate(
            "/me/onlineMeetings/getAllTranscripts",
            limit=self._settings.M365_MAX_LIMIT,
        )

        recent = self._filtered_since_and_truncated(
            raw_transcripts, since=effective_since, bounded_limit=bounded_limit
        )

        notes: list[MeetingNote] = []
        for raw in recent:
            content_response = await client.get(
                f"/me/onlineMeetings/{raw['meetingId']}/transcripts/"
                f"{raw['id']}/content"
            )
            notes.append(map_meeting_note(raw, content_response.text))
        return notes
