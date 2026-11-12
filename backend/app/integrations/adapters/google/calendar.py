"""`CalendarReaderPort` over the Google Calendar API (change
16-adapter-google, design.md "calendar.py"). Queries the connected
account's primary calendar (``calendars/primary/events``) bounded by
``timeMin``/``timeMax`` derived from ``since``/``limit`` (design.md, tabla
de traducción por puerto: ``since`` → ``timeMin``, ``timeMax`` = now).
"""

from datetime import UTC, datetime
from typing import Any

from app.integrations.adapters.google.ports_base import _GooglePortBase
from app.integrations.dtos import CalendarEvent
from app.integrations.ports import AccessContext


def _rfc3339(value: datetime) -> str:
    """Format ``value`` as the UTC RFC 3339 timestamp Calendar's
    ``timeMin``/``timeMax`` expect."""

    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _event_datetime(node: dict[str, Any]) -> datetime:
    """Parse a Calendar ``start``/``end`` node — either a timed event
    (``dateTime``, ISO-8601 with an offset) or an all-day event (``date``,
    a bare ``YYYY-MM-DD``, treated as UTC midnight)."""

    if "dateTime" in node:
        return datetime.fromisoformat(node["dateTime"].replace("Z", "+00:00"))
    return datetime.fromisoformat(node["date"]).replace(tzinfo=UTC)


def map_calendar_event(raw: dict[str, Any]) -> CalendarEvent:
    """Map a single `events.list` item to a :class:`CalendarEvent`."""

    return CalendarEvent(
        external_id=str(raw["id"]),
        title=str(raw.get("summary") or ""),
        starts_at=_event_datetime(raw["start"]),
        ends_at=_event_datetime(raw["end"]),
        organizer=str((raw.get("organizer") or {}).get("email") or ""),
        attendees=tuple(
            str(attendee["email"])
            for attendee in raw.get("attendees") or []
            if attendee.get("email")
        ),
        location=raw.get("location"),
    )


class GoogleCalendarReader(_GooglePortBase):
    """``CalendarReaderPort`` over the Google Calendar API (scope
    ``calendar.readonly``)."""

    _base_url_setting = "GOOGLE_CALENDAR_BASE_URL"

    async def list_events(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int | None = None
    ) -> list[CalendarEvent]:
        bounded_limit = self._bounded_limit(limit)
        client = self._client(ctx)

        raw_items = await client.paginate(
            "/calendars/primary/events",
            params=self._params(since, bounded_limit),
            items_key="items",
            limit=bounded_limit,
        )
        return [map_calendar_event(item) for item in raw_items]

    def _params(self, since: datetime | None, bounded_limit: int) -> dict[str, str]:
        start = self._since_or_default(since)
        now = datetime.now(UTC)
        return {
            "timeMin": _rfc3339(start),
            "timeMax": _rfc3339(now),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": str(self._page_size(bounded_limit)),
        }
