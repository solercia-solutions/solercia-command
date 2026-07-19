"""Microsoft Graph HTTP client (change 15-adapter-microsoft365, design.md
"GraphClient httpx inyectable"). Every port (mail/calendar/planner/meeting
notes, Lotes 4-7) builds requests through this ONE class so pagination, the
TLS/anti-SSRF boundary and — from Lote 2 onward — 401/429 resilience live in
a single place instead of being duplicated per capability.

The transport is injectable (``transport=httpx.MockTransport(...)``) so the
test suite never touches the real network (design.md, "cero red en CI").
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.ports import AccessContext


class GraphHostMismatchError(Exception):
    """Raised when a Graph response's ``@odata.nextLink`` points to a host
    other than the configured ``M365_GRAPH_BASE_URL`` (anti-SSRF/host fijo,
    design.md Threat Matrix). The mismatched URL is NEVER requested — this
    is raised BEFORE the client follows it."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(
            f"@odata.nextLink apunta a un host no permitido: {url!r}"
        )


def _require_https(url: str, field_name: str) -> None:
    """Fail fast when ``url`` (an ``M365_*_BASE_URL`` setting) is not
    ``https://`` (design.md Threat Matrix, "TLS obligatorio")."""

    if urlsplit(url).scheme != "https":
        raise ValueError(
            f"{field_name} debe usar https, recibido: {url!r}"
        )


class GraphClient:
    """Thin async wrapper over Microsoft Graph with an injectable transport
    and an injectable ``sleep`` (used by the 429 backoff added in Lote 2)."""

    def __init__(
        self,
        ctx: AccessContext,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        settings: Settings = default_settings,
    ) -> None:
        _require_https(settings.M365_GRAPH_BASE_URL, "M365_GRAPH_BASE_URL")
        _require_https(settings.M365_LOGIN_BASE_URL, "M365_LOGIN_BASE_URL")

        self._ctx = ctx
        self._settings = settings
        self._sleep = sleep
        self._allowed_host = urlsplit(settings.M365_GRAPH_BASE_URL).netloc
        self._http = httpx.AsyncClient(
            base_url=settings.M365_GRAPH_BASE_URL,
            timeout=settings.M365_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def paginate(self, url: str, *, limit: int) -> list[dict[str, Any]]:
        """Follow ``@odata.nextLink`` from ``url`` until ``limit`` items are
        collected or the response stops paginating, whichever comes first.

        Bounded by ``M365_MAX_PAGES`` regardless of ``limit`` — a
        misbehaving/adversarial server that always returns another
        ``nextLink`` can never trap this in an infinite loop. Each
        ``nextLink``'s host is validated against ``M365_GRAPH_BASE_URL``
        BEFORE it is ever requested (:class:`GraphHostMismatchError`).
        """

        items: list[dict[str, Any]] = []
        next_url: str | None = url
        pages = 0

        while (
            next_url is not None
            and len(items) < limit
            and pages < self._settings.M365_MAX_PAGES
        ):
            response = await self._get(next_url)
            payload = response.json()
            items.extend(payload.get("value", []))
            pages += 1

            next_url = payload.get("@odata.nextLink")
            if next_url is not None:
                self._assert_allowed_host(next_url)

        return items[:limit]

    async def _get(self, url: str) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._ctx.access_token}"}
        return await self._http.get(url, headers=headers)

    def _assert_allowed_host(self, url: str) -> None:
        host = urlsplit(url).netloc
        if host != self._allowed_host:
            raise GraphHostMismatchError(url)

    async def aclose(self) -> None:
        """Release the underlying ``httpx.AsyncClient``'s connections."""

        await self._http.aclose()
