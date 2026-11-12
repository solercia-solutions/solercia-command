"""`MailReaderPort` over the Gmail API (change 16-adapter-google, design.md
"mail.py"). ``users.messages.list`` only returns message ids/threadIds —
this port follows up with a ``users.messages.get?format=full`` per id and
maps the full resource (headers + ``mime.body_text``) to a
:class:`MailMessage`, the SAME N+1 shape Gmail's own API forces on any
reader that needs a message's body (design.md File Changes, "mail.py").
"""

import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.integrations.adapters.google import mime
from app.integrations.adapters.google.ports_base import _GooglePortBase
from app.integrations.dtos import MailMessage
from app.integrations.ports import AccessContext
from app.shared.exceptions import AppException

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"<([^>]+)>")


def _extract_email(header_value: str) -> str:
    """Pull the bracketed address out of a `"Name <email>"` header value;
    falls back to the raw value when there is no `<...>` (a bare address)."""

    match = _EMAIL_RE.search(header_value)
    return match.group(1).strip() if match else header_value.strip()


def _header(headers: list[dict[str, Any]], name: str) -> str:
    for header in headers:
        if str(header.get("name", "")).lower() == name.lower():
            return str(header.get("value") or "")
    return ""


def _received_at(raw: dict[str, Any]) -> datetime:
    """Gmail's own ``internalDate`` (epoch millis, as a STRING) is the
    authoritative received timestamp — more reliable than parsing the
    ``Date`` header's free-form RFC 2822 text."""

    return datetime.fromtimestamp(int(raw["internalDate"]) / 1000, tz=UTC)


def map_mail_message(raw: dict[str, Any]) -> MailMessage:
    """Map a single `users.messages.get?format=full` resource to a
    :class:`MailMessage`. Gmail's own ``labelIds``/``threadId`` are
    intentionally NOT read here — they never leave this adapter as a
    "folder" concept (spec.md, "Labels no se traducen a carpeta")."""

    payload = raw.get("payload") or {}
    headers = payload.get("headers") or []
    to_header = _header(headers, "To")
    recipients = tuple(
        _extract_email(part) for part in to_header.split(",") if part.strip()
    )

    return MailMessage(
        external_id=str(raw["id"]),
        subject=_header(headers, "Subject"),
        sender=_extract_email(_header(headers, "From")),
        recipients=recipients,
        received_at=_received_at(raw),
        snippet=str(raw.get("snippet") or ""),
        body_text=mime.body_text(payload) or None,
    )


class GmailMailReader(_GooglePortBase):
    """``MailReaderPort`` over the Gmail API (scope ``gmail.readonly``)."""

    _base_url_setting = "GOOGLE_GMAIL_BASE_URL"

    async def list_messages(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int | None = None
    ) -> list[MailMessage]:
        bounded_limit = self._bounded_limit(limit)
        client = self._client(ctx)

        listed = await client.paginate(
            "/users/me/messages",
            params=self._list_params(since, bounded_limit),
            items_key="messages",
            limit=bounded_limit,
        )

        messages: list[MailMessage] = []
        for item in listed:
            msg_id = str(item["id"])
            try:
                response = await client.get(
                    f"/users/me/messages/{msg_id}", params={"format": "full"}
                )
            except AppException:
                # WARNING 16-adapter-google: un mensaje puntual puede fallar
                # (ej. borrado entre `messages.list` y `messages.get`) sin
                # que eso deba tumbar TODO el listado — se omite y se sigue
                # con el resto (aislamiento N+1). Nunca se loguea el token.
                logger.warning(
                    "No fue posible obtener el mensaje de Gmail %s; se omite del listado.",
                    msg_id,
                )
                continue
            messages.append(map_mail_message(response.json()))
        return messages

    def _list_params(
        self, since: datetime | None, bounded_limit: int
    ) -> dict[str, str]:
        effective_since = self._since_or_default(since)
        epoch = int(effective_since.timestamp())
        return {
            "q": f"after:{epoch}",
            "maxResults": str(self._page_size(bounded_limit)),
        }
