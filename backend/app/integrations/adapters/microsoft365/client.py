"""Microsoft Graph HTTP client (change 15-adapter-microsoft365, design.md
"GraphClient httpx inyectable"). Every port (mail/calendar/planner/meeting
notes, Lotes 4-7) builds requests through this ONE class so pagination, the
TLS/anti-SSRF boundary and — from Lote 2 onward — 401/429 resilience live in
a single place instead of being duplicated per capability.

The transport is injectable (``transport=httpx.MockTransport(...)``) so the
test suite never touches the real network (design.md, "cero red en CI").
"""

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.microsoft365 import errors
from app.integrations.dtos import OAuthTokens
from app.integrations.ports import AccessContext

logger = logging.getLogger(__name__)

# Body preview cap for the 4xx/5xx warning log below (avoid dumping a large
# Graph error payload into the logs).
_LOGGED_BODY_PREVIEW_CHARS = 200


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
    """Thin async wrapper over Microsoft Graph with an injectable transport,
    an injectable ``sleep`` (429 backoff never waits for real in tests) and
    an optional ``refresh`` callable used to recover from an expired access
    token (401 → refresh → single retry, M365-R3).

    ``refresh`` is deliberately a plain callable — not a dependency on
    ``oauth.py``/``adapter.py`` (Lote 3) — so this module has no import
    cycle with the rest of the package; the adapter wires
    ``self.refresh`` (its own OAuth method) into every ``GraphClient`` it
    builds.
    """

    def __init__(
        self,
        ctx: AccessContext,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        settings: Settings = default_settings,
        refresh: Callable[[str], Awaitable[OAuthTokens]] | None = None,
    ) -> None:
        _require_https(settings.M365_GRAPH_BASE_URL, "M365_GRAPH_BASE_URL")
        _require_https(settings.M365_LOGIN_BASE_URL, "M365_LOGIN_BASE_URL")

        self._ctx = ctx
        self._settings = settings
        self._sleep = sleep
        self._refresh = refresh
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

    async def get(self, url: str) -> httpx.Response:
        """GET a single (non-paginated) Graph resource with the SAME
        resilience boundary as :meth:`paginate` — used by ports that fetch
        one resource directly (e.g. a transcript's ``.../content``,
        Lote 7), not a ``value``-paginated collection."""

        return await self._get(url)

    async def _get(self, url: str) -> httpx.Response:
        """GET ``url`` with the resilience boundary applied: a single
        refresh-and-retry on ``401``, a bounded ``Retry-After`` backoff on
        repeated ``429``, and a ``403``→``capability_unavailable`` /
        other-``4xx``/``5xx``→``provider_unavailable`` mapping so every
        port gets the SAME controlled-error contract (M365-R3, M365-R6,
        M365-R7)."""

        used_refresh = False
        throttle_attempts = 0

        while True:
            response = await self._raw_get(url)

            if response.status_code == 401:
                if used_refresh:
                    raise errors.oauth_token_invalid()
                used_refresh = True
                await self._refresh_tokens()
                continue

            if response.status_code == 429:
                throttle_attempts += 1
                if throttle_attempts > self._settings.M365_MAX_RETRIES:
                    raise errors.provider_throttled()
                await self._sleep(self._retry_after_seconds(response))
                continue

            if response.status_code == 403:
                raise errors.capability_unavailable()

            if response.status_code >= 400:
                self._log_error_response(response)
                if response.status_code >= 500:
                    raise errors.provider_unavailable()  # 5xx: RETRYABLE
                # Remaining 4xx (400/404/405/409...): the request itself is
                # rejected/invalid, NEVER retryable as-is.
                raise errors.provider_request_failed()

            return response

    async def _raw_get(self, url: str) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._ctx.access_token}"}
        return await self._http.get(url, headers=headers)

    async def _refresh_tokens(self) -> None:
        """Exchange the current ``refresh_token`` for a fresh access token
        via the injected ``refresh`` callable, update ``self._ctx`` and hand
        the rotated tokens to ``ctx.on_tokens_refreshed`` when present.

        Raises :func:`errors.oauth_token_invalid` — never loops — when no
        refresh is possible (missing callable/refresh token) or the
        provider rejects the refresh (revoked token)."""

        if self._refresh is None or self._ctx.refresh_token is None:
            raise errors.oauth_token_invalid()

        try:
            new_tokens = await self._refresh(self._ctx.refresh_token)
        except Exception as exc:
            raise errors.oauth_token_invalid() from exc

        self._ctx = dataclasses.replace(
            self._ctx,
            access_token=new_tokens.access_token,
            refresh_token=new_tokens.refresh_token or self._ctx.refresh_token,
        )
        if self._ctx.on_tokens_refreshed is not None:
            await self._ctx.on_tokens_refreshed(new_tokens)

    @staticmethod
    def _log_error_response(response: httpx.Response) -> None:
        """Log a 4xx/5xx status + truncated body — NEVER the request's
        ``Authorization`` header/access token (only ``response.text`` is
        read here)."""

        body_preview = response.text[:_LOGGED_BODY_PREVIEW_CHARS]
        logger.warning(
            "Microsoft Graph respondió %s para %s: %s",
            response.status_code,
            response.request.url if response.request else "?",
            body_preview,
        )

    def _retry_after_seconds(self, response: httpx.Response) -> float:
        header = response.headers.get("Retry-After")
        seconds = 1.0
        if header is not None:
            try:
                seconds = float(header)
            except ValueError:
                seconds = 1.0
        # Clamp: an abusive `Retry-After` (e.g. 3600s) never sleeps longer
        # than `M365_MAX_BACKOFF_SECONDS`.
        return min(seconds, self._settings.M365_MAX_BACKOFF_SECONDS)

    def _assert_allowed_host(self, url: str) -> None:
        host = urlsplit(url).netloc
        if host != self._allowed_host:
            raise GraphHostMismatchError(url)

    async def aclose(self) -> None:
        """Release the underlying ``httpx.AsyncClient``'s connections."""

        await self._http.aclose()
