"""Read-only port implementations over Microsoft Graph (change
15-adapter-microsoft365, design.md). Each class implements ONE of the 14's
port ``Protocol``s (``MailReaderPort``/``CalendarReaderPort``/
``ExternalTaskReaderPort``/``MeetingNotesReaderPort``) against a Graph
endpoint, via the shared :class:`GraphClient` (pagination + TLS/anti-SSRF +
401/429 resilience) and ``mappers.py`` (Graph JSON → DTO).

``_GraphPortBase`` centralizes the ONE piece every port repeats: building a
:class:`GraphClient` bound to the port's own ``settings``/``transport`` and
wired with ``oauth.refresh`` as the 401 recovery callable — every subclass
only adds its endpoint path, query and mapper.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.microsoft365 import oauth
from app.integrations.adapters.microsoft365.client import GraphClient
from app.integrations.adapters.microsoft365.mappers import map_mail_message
from app.integrations.dtos import MailMessage, OAuthTokens
from app.integrations.ports import AccessContext


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
        return min(self._bounded_limit(limit), 50) or 1

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
