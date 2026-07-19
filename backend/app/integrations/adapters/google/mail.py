"""`MailReaderPort` over the Gmail API (change 16-adapter-google, design.md
"mail.py"). ``users.messages.list`` only returns message ids/threadIds —
this port follows up with a ``users.messages.get?format=full`` per id and
maps the full resource (headers + ``mime.body_text``) to a
:class:`MailMessage`, the SAME N+1 shape Gmail's own API forces on any
reader that needs a message's body (design.md File Changes, "mail.py").
"""

import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.google import mime, oauth
from app.integrations.adapters.google.client import GOOGLE_PAGE_CAP, GoogleClient
from app.integrations.dtos import MailMessage, OAuthTokens
from app.integrations.ports import AccessContext

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


class GmailMailReader:
    """``MailReaderPort`` over the Gmail API (scope ``gmail.readonly``)."""

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def list_messages(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
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
            response = await client.get(
                f"/users/me/messages/{item['id']}", params={"format": "full"}
            )
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

    def _bounded_limit(self, limit: int) -> int:
        return max(0, min(limit, self._settings.GOOGLE_MAX_LIMIT))

    def _page_size(self, limit: int) -> int:
        return min(self._bounded_limit(limit), GOOGLE_PAGE_CAP) or 1

    def _since_or_default(self, since: datetime | None) -> datetime:
        if since is not None:
            return since
        return datetime.now(UTC) - timedelta(
            days=self._settings.GOOGLE_DEFAULT_SINCE_DAYS
        )

    def _refresh(self) -> Callable[[str], Awaitable[OAuthTokens]]:
        async def _call(refresh_token: str) -> OAuthTokens:
            return await oauth.refresh(
                refresh_token, settings=self._settings, transport=self._transport
            )

        return _call

    def _client(self, ctx: AccessContext) -> GoogleClient:
        return GoogleClient(
            ctx,
            base_url=self._settings.GOOGLE_GMAIL_BASE_URL,
            transport=self._transport,
            settings=self._settings,
            refresh=self._refresh(),
        )
