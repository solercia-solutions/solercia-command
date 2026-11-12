"""Translate Solercia Connect records into Command's neutral DTOs.

Connect already normalizes every provider onto one shape and stamps each record
with provenance, so this module is a rename, not a second normalization pass.
It stays a pure function of the payload: no clock, no network, no defaults that
invent a value the source never carried.
"""

import re
from datetime import datetime
from typing import Any

from app.integrations.adapters.solercia_connect.errors import SolerciaConnectProtocolError
from app.integrations.dtos import CalendarEvent, MailMessage, MeetingNote

_SNIPPET_LENGTH = 280
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def _require(record: dict[str, Any], key: str) -> Any:
    if key not in record:
        raise SolerciaConnectProtocolError(f"Solercia Connect record is missing {key!r}")
    return record[key]


def _timestamp(value: Any, key: str) -> datetime:
    if not isinstance(value, str):
        raise SolerciaConnectProtocolError(f"Solercia Connect {key} is not a timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as failure:
        raise SolerciaConnectProtocolError(
            f"Solercia Connect {key} is not an ISO 8601 timestamp"
        ) from failure
    if parsed.tzinfo is None:
        raise SolerciaConnectProtocolError(f"Solercia Connect {key} is not timezone-aware")
    return parsed


def _address(value: Any) -> str | None:
    """Read one address from Connect's ``{address, name}`` shape."""
    if not isinstance(value, dict):
        return None
    address = value.get("address")
    return address if isinstance(address, str) and address.strip() else None


def _addresses(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    found = [_address(entry) for entry in value]
    return tuple(entry for entry in found if entry is not None)


def plain_text(body: str, body_format: str | None) -> str:
    """Reduce a message body to text.

    Command's ``MailMessage`` carries text, not markup. Handing it raw HTML
    would push the stripping onto every reader, and each would do it slightly
    differently.
    """
    if body_format and body_format.strip().casefold() == "html":
        body = _TAG.sub(" ", body)
    return _WHITESPACE.sub(" ", body).strip()


# Connect's ``folder`` vocabulary (mail-record-contract spec) → direction
# relative to the account that read it.
_DIRECTION_BY_FOLDER: dict[str, str] = {"inbox": "inbound", "sent": "outbound"}


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _texts(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    found = [_text(entry) for entry in value]
    return tuple(entry for entry in found if entry is not None)


def _optional_timestamp(record: dict[str, Any], key: str) -> datetime | None:
    value = record.get(key)
    return None if value is None else _timestamp(value, key)


def _direction(record: dict[str, Any], listed_from: str | None) -> str | None:
    """The record's own ``folder`` wins: Connect stamps it explicitly. The
    folder the port listed it from is the fallback for records that predate
    that field. Anything else is left unknown, never guessed."""
    folder = _text(record.get("folder"))
    if folder is not None and folder.casefold() in _DIRECTION_BY_FOLDER:
        return _DIRECTION_BY_FOLDER[folder.casefold()]
    return _DIRECTION_BY_FOLDER.get(listed_from) if listed_from else None


def map_mail_message(record: dict[str, Any], *, listed_from: str | None = None) -> MailMessage:
    """Map one mail record. ``listed_from`` is the Connect folder (``inbox``
    or ``sent``) the record was read from, when the port knows it."""
    body = _require(record, "body")
    if not isinstance(body, str):
        raise SolerciaConnectProtocolError("Solercia Connect mail body is not text")
    text = plain_text(body, record.get("body_format"))
    sender = _address(record.get("sender"))
    sent_at = _timestamp(_require(record, "sent_at"), "sent_at")
    has_attachments = record.get("has_attachments")
    return MailMessage(
        external_id=str(_require(record, "id")),
        subject=str(record.get("subject") or ""),
        # An address Connect could not observe is left empty rather than
        # filled with the account that asked, which would misattribute it.
        sender=sender or "",
        recipients=_addresses(record.get("to")),
        received_at=sent_at,
        snippet=text[:_SNIPPET_LENGTH],
        body_text=text or None,
        conversation_id=_text(record.get("conversation_id")),
        internet_message_id=_text(record.get("internet_message_id")),
        # Connect does not emit these today; read them if a route ever does.
        in_reply_to=_text(record.get("in_reply_to")),
        references=_texts(record.get("references")),
        cc=_addresses(record.get("cc")),
        direction=_direction(record, listed_from),
        sent_at=sent_at,
        delivered_at=_optional_timestamp(record, "received_at"),
        has_attachments=has_attachments if isinstance(has_attachments, bool) else None,
    )


def map_calendar_event(record: dict[str, Any]) -> CalendarEvent:
    return CalendarEvent(
        external_id=str(_require(record, "id")),
        title=str(record.get("title") or ""),
        starts_at=_timestamp(_require(record, "start"), "start"),
        ends_at=_timestamp(_require(record, "end"), "end"),
        organizer=_address(record.get("organizer")) or "",
        attendees=_addresses(record.get("attendees")),
        # Connect does not observe a location on this surface; reporting one
        # would be inventing it.
        location=None,
    )


def map_meeting_note(record: dict[str, Any]) -> MeetingNote:
    """Map one transcript.

    ``occurred_at`` comes from the recording, which is the only timestamp the
    transcript itself is anchored to. A transcript without one is refused
    rather than stamped with "now": a note that claims to be from today when
    it is from last month is worse than an absent note.
    """
    recorded_at = record.get("recorded_at")
    if recorded_at is None:
        raise SolerciaConnectProtocolError(
            "Solercia Connect transcript carries no recording timestamp"
        )
    speakers = record.get("speakers")
    participants = (
        tuple(entry for entry in speakers if isinstance(entry, str) and entry.strip())
        if isinstance(speakers, list)
        else ()
    )
    content = _require(record, "content")
    if not isinstance(content, str):
        raise SolerciaConnectProtocolError("Solercia Connect transcript content is not text")
    return MeetingNote(
        external_id=str(_require(record, "id")),
        meeting_title=str(record.get("display_name") or ""),
        occurred_at=_timestamp(recorded_at, "recorded_at"),
        transcript=content,
        participants=participants,
    )
