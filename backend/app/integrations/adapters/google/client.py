"""Google API HTTP client (change 16-adapter-google, design.md "GoogleClient
httpx inyectable"). Every port (mail/calendar/meeting_notes, Lotes 4-5)
builds requests through this ONE class so pagination, the TLS boundary and
401/429/403-cuota resilience live in a single place instead of being
duplicated per capability — same role as ``adapters/microsoft365/client.py``'s
``GraphClient``.

The transport is injectable (``transport=httpx.MockTransport(...)``) so the
test suite never touches the real network (design.md, "cero red en CI").

**Divergencia estructural frente a Graph (documentada, no un olvido)**:
Microsoft Graph paginates via ``@odata.nextLink`` — a FULL URL the client
must follow, which is why ``GraphClient`` validates that URL's host before
ever requesting it (``GraphHostMismatchError``). Google's three APIs
(Gmail/Calendar/Drive) instead paginate via ``nextPageToken`` — an OPAQUE
STRING sent back as the ``pageToken`` query parameter on the SAME
``base_url`` this client was constructed with. There is no provider-supplied
URL to validate: every request this client ever issues is built from
``base_url`` (fixed at construction, HTTPS-enforced) + a caller-supplied
``path``/``params`` literal, never from response data. The anti-SSRF
boundary is therefore structural here, not a runtime host check.
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
from app.integrations.adapters.google import errors
from app.integrations.dtos import OAuthTokens
from app.integrations.ports import AccessContext

logger = logging.getLogger(__name__)

# Body preview cap for the 4xx/5xx warning log below (avoid dumping a large
# Google error payload into the logs).
_LOGGED_BODY_PREVIEW_CHARS = 200

# Google's own per-request page-size ceiling used by callers building
# `maxResults`/`pageSize` params — a port never asks for more items per page
# than this, regardless of `limit` (named constant, mirrors `GRAPH_PAGE_CAP`
# in the 15's `ports.py`).
GOOGLE_PAGE_CAP = 100

# `error.errors[].reason` values Google returns on `403` that mean "cuota
# excedida, reintenta con backoff" — every OTHER `403` reason means the
# connected account genuinely lacks permission for the resource requested.
_THROTTLE_REASONS = frozenset({"rateLimitExceeded", "userRateLimitExceeded"})


def _require_https(url: str, field_name: str) -> None:
    """Fail fast when ``url`` is not ``https://`` (anti-SSRF/TLS
    obligatorio, mismo criterio que ``GraphClient._require_https``)."""

    if urlsplit(url).scheme != "https":
        raise ValueError(f"{field_name} debe usar https, recibido: {url!r}")


class GoogleClient:
    """Thin async wrapper over a single Google API (Gmail, Calendar or
    Drive — each port constructs its OWN instance with that API's
    ``base_url``) with an injectable transport, an injectable ``sleep``
    (429/403-cuota backoff never waits for real in tests) and an optional
    ``refresh`` callable used to recover from an expired access token
    (401 → refresh → single retry, GA-R3).

    ``refresh`` is deliberately a plain callable — not a dependency on
    ``oauth.py``/``adapter.py`` — so this module has no import cycle with
    the rest of the package; each port wires ``oauth.refresh`` into every
    ``GoogleClient`` it builds (same pattern as the 15's ``_GraphPortBase``).
    """

    def __init__(
        self,
        ctx: AccessContext,
        *,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        settings: Settings = default_settings,
        refresh: Callable[[str], Awaitable[OAuthTokens]] | None = None,
    ) -> None:
        _require_https(base_url, "base_url")

        self._ctx = ctx
        self._settings = settings
        self._sleep = sleep
        self._refresh = refresh
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=settings.GOOGLE_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def paginate(
        self, path: str, *, params: dict[str, str], items_key: str, limit: int
    ) -> list[dict[str, Any]]:
        """Follow ``nextPageToken`` from ``path``/``params`` until ``limit``
        items are collected or the response stops paginating, whichever
        comes first.

        Bounded by ``GOOGLE_MAX_PAGES`` regardless of ``limit`` — a
        misbehaving/adversarial server that always returns another
        ``nextPageToken`` can never trap this in an infinite loop.
        """

        items: list[dict[str, Any]] = []
        page_token: str | None = None
        pages = 0

        while len(items) < limit and pages < self._settings.GOOGLE_MAX_PAGES:
            query = dict(params)
            if page_token is not None:
                query["pageToken"] = page_token

            response = await self._get(path, query)
            payload = response.json()
            items.extend(payload.get(items_key, []) or [])
            pages += 1

            page_token = payload.get("nextPageToken")
            if page_token is None:
                break

        return items[:limit]

    async def get(
        self, path: str, *, params: dict[str, str] | None = None
    ) -> httpx.Response:
        """GET a single (non-paginated) Google resource with the SAME
        resilience boundary as :meth:`paginate` — used by ports that fetch
        one resource directly (a Gmail message by id, a Doc's
        ``.../export``), not an ``items``-paginated collection."""

        return await self._get(path, params or {})

    async def _get(self, path: str, params: dict[str, str]) -> httpx.Response:
        """GET ``path``/``params`` with the resilience boundary applied: a
        single refresh-and-retry on ``401``, a bounded backoff on repeated
        ``429``/``403`` cuota, and Google's own error taxonomy
        (``errors.error_for_response``) for everything else — so every port
        gets the SAME controlled-error contract (GA-R3, GA-R7)."""

        used_refresh = False
        throttle_attempts = 0

        while True:
            response = await self._raw_get(path, params)

            if response.status_code == 401:
                if used_refresh:
                    raise errors.oauth_token_invalid()
                used_refresh = True
                await self._refresh_tokens()
                continue

            if response.status_code in (429, 403):
                mapped = errors.error_for_response(
                    response.status_code, self._safe_json(response)
                )
                if mapped.code == "provider_throttled":
                    throttle_attempts += 1
                    if throttle_attempts > self._settings.GOOGLE_MAX_RETRIES:
                        raise mapped
                    await self._sleep(self._retry_after_seconds(response))
                    continue
                self._log_error_response(response)
                raise mapped

            if response.status_code >= 400:
                self._log_error_response(response)
                raise errors.error_for_response(
                    response.status_code, self._safe_json(response)
                )

            return response

    async def _raw_get(self, path: str, params: dict[str, str]) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._ctx.access_token}"}
        return await self._http.get(path, params=params, headers=headers)

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
    def _safe_json(response: httpx.Response) -> dict[str, Any] | None:
        try:
            payload = response.json()
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _log_error_response(response: httpx.Response) -> None:
        """Log a 4xx/5xx status + truncated body — NEVER the request's
        ``Authorization`` header/access token (only ``response.text`` is
        read here)."""

        body_preview = response.text[:_LOGGED_BODY_PREVIEW_CHARS]
        logger.warning(
            "La API de Google respondió %s para %s: %s",
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
        # than `GOOGLE_MAX_BACKOFF_SECONDS`.
        return min(seconds, self._settings.GOOGLE_MAX_BACKOFF_SECONDS)

    async def aclose(self) -> None:
        """Release the underlying ``httpx.AsyncClient``'s connections."""

        await self._http.aclose()
