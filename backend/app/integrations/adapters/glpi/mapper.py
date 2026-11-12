"""GLPI JSON -> agnostic DTO translation (change 17-adapter-glpi, design.md
"mapper.py"). PURE functions, no I/O, no ORM — takes the raw dicts
``client.py`` already fetched and returns ``Ticket``/``ExternalPerson``
instances (``app/integrations/dtos.py``).
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.integrations.dtos import ExternalPerson, Ticket


def _pick_default_email(emails_json: Sequence[dict[str, Any]]) -> str | None:
    """Return the address flagged ``is_default``; falls back to the FIRST
    address when none is flagged (GLPI's ``UserEmail`` collection may list
    several without an explicit default)."""

    for entry in emails_json:
        if entry.get("is_default"):
            email = entry.get("email")
            return str(email) if email else None
    if emails_json:
        email = emails_json[0].get("email")
        return str(email) if email else None
    return None


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def map_person(
    user_json: dict[str, Any],
    emails_json: Sequence[dict[str, Any]],
    *,
    document_field: str,
) -> ExternalPerson:
    """Translate a GLPI ``User`` (+ its ``UserEmail`` collection) into an
    :class:`ExternalPerson` (IP17-R1). ``document_field`` is the GLPI field
    name carrying the identity document — configurable per connector
    (``connectors.settings.document_field``, default
    ``registration_number``, user-homologation spec).
    """

    external_id = str(user_json.get("id", ""))
    firstname = (user_json.get("firstname") or "").strip()
    realname = (user_json.get("realname") or "").strip()
    display_name = " ".join(part for part in (firstname, realname) if part) or None

    return ExternalPerson(
        external_id=external_id,
        display_name=display_name,
        email=_pick_default_email(emails_json),
        document=_clean_str(user_json.get(document_field)),
    )


def _parse_glpi_datetime(raw: str | None) -> datetime:
    """Parse a GLPI ``"YYYY-MM-DD HH:MM:SS"`` timestamp as UTC. Falls back
    to "now" when the field is absent — a ticket always needs SOME
    ``created_at`` (``Ticket`` is not optional on this field) and GLPI's
    own ``date`` is occasionally blank on draft/malformed tickets."""

    if not raw:
        return datetime.now(UTC)
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


def map_ticket(
    ticket_json: dict[str, Any],
    *,
    assignees: Sequence[ExternalPerson],
    requester: str | None,
) -> Ticket:
    """Translate a raw GLPI ``Ticket`` row (plus its already-resolved
    ``assignees``/``requester``) into the agnostic :class:`Ticket` DTO.
    ``key`` is synthesized as ``GLPI-{id}`` — GLPI's REST API exposes no
    separate human-facing key distinct from the numeric ``id``.
    """

    priority = ticket_json.get("priority")
    return Ticket(
        external_id=str(ticket_json["id"]),
        key=f"GLPI-{ticket_json['id']}",
        summary=ticket_json.get("name") or "",
        status=str(ticket_json.get("status", "")),
        priority=str(priority) if priority is not None else None,
        requester=requester,
        created_at=_parse_glpi_datetime(ticket_json.get("date")),
        assignees=tuple(assignees),
    )
