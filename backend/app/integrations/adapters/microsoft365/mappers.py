"""Graph JSON → the 14's provider-agnostic DTOs (change
15-adapter-microsoft365, design.md "mappers.py"). Each function takes a
SINGLE raw Graph resource (already extracted from a `value` page by
`GraphClient.paginate`) and returns the matching frozen dataclass from
`app/integrations/dtos.py` — Graph's own field names/shapes never leak
past this module.
"""

from datetime import UTC, datetime
from typing import Any

from app.integrations.dtos import CalendarEvent, MailMessage


def _graph_datetime(value: str) -> datetime:
    """Parse a Graph ISO-8601 UTC timestamp (``...Z`` suffix)."""

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _graph_datetime_timezone(node: dict[str, Any]) -> datetime:
    """Parse a Graph ``{"dateTime": ..., "timeZone": ...}`` node — Graph's
    calendar endpoints return a timezone-NAIVE ``dateTime`` string paired
    with a separate ``timeZone`` name (no ``Prefer: outlook.timezone``
    header is sent, so Graph always answers in ``UTC`` here)."""

    naive = datetime.fromisoformat(node["dateTime"])
    if node.get("timeZone", "UTC") == "UTC":
        return naive.replace(tzinfo=UTC)
    return naive


def _email_address(node: dict[str, Any] | None) -> str:
    if not node:
        return ""
    return str(node.get("emailAddress", {}).get("address", ""))


def map_mail_message(raw: dict[str, Any]) -> MailMessage:
    """Map a single `/me/messages` item to a :class:`MailMessage`."""

    return MailMessage(
        external_id=str(raw["id"]),
        subject=str(raw.get("subject") or ""),
        sender=_email_address(raw.get("from")),
        recipients=tuple(
            _email_address(recipient) for recipient in raw.get("toRecipients", [])
        ),
        received_at=_graph_datetime(raw["receivedDateTime"]),
        snippet=str(raw.get("bodyPreview") or ""),
        body_text=(raw.get("body") or {}).get("content"),
    )


def map_calendar_event(raw: dict[str, Any]) -> CalendarEvent:
    """Map a single `/me/calendarView` item to a :class:`CalendarEvent`."""

    location = raw.get("location") or {}
    return CalendarEvent(
        external_id=str(raw["id"]),
        title=str(raw.get("subject") or ""),
        starts_at=_graph_datetime_timezone(raw["start"]),
        ends_at=_graph_datetime_timezone(raw["end"]),
        organizer=_email_address(raw.get("organizer")),
        attendees=tuple(
            _email_address(attendee) for attendee in raw.get("attendees", [])
        ),
        location=location.get("displayName"),
    )
