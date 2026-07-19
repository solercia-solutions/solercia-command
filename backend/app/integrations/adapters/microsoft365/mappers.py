"""Graph JSON → the 14's provider-agnostic DTOs (change
15-adapter-microsoft365, design.md "mappers.py"). Each function takes a
SINGLE raw Graph resource (already extracted from a `value` page by
`GraphClient.paginate`) and returns the matching frozen dataclass from
`app/integrations/dtos.py` — Graph's own field names/shapes never leak
past this module.
"""

from datetime import datetime
from typing import Any

from app.integrations.dtos import MailMessage


def _graph_datetime(value: str) -> datetime:
    """Parse a Graph ISO-8601 UTC timestamp (``...Z`` suffix)."""

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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
