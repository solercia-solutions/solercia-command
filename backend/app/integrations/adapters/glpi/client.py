"""GLPI HTTP client (change 17-adapter-glpi, design.md "Cliente GLPI base").
Thin async wrapper over ``apirest.php``'s session lifecycle
(``initSession``/``killSession``) and its `Range`-header pagination for
``GET /Ticket``. Every other port method (Lote 6's mapper: ``Ticket_User``,
``User``, ``UserEmail``) builds requests through this SAME class so the
anti-SSRF boundary and pagination live in ONE place.

The transport is injectable (``transport=httpx.MockTransport(...)``) so the
test suite never touches the real network (design.md, "cero red en CI").

Unlike ``M365``/``Google`` (a single, fixed, ``https://``-only provider
host), GLPI's ``base_url`` is PER-CONNECTOR — an admin configures which
GLPI instance a connector talks to (``connectors.settings.base_url``). That
makes it caller-controlled input, so the anti-SSRF boundary here is an
ALLOWLIST (``GLPI_BASE_URL_ALLOWLIST``, analogous to
``OAUTH_REDIRECT_ALLOWLIST``) rather than a single hardcoded host —
:class:`GlpiConfigError` is raised in the constructor, BEFORE any request
is ever attempted (Threat Matrix, "SSRF").
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.config import settings as default_settings


class GlpiConfigError(ValueError):
    """Raised when a GLPI connector's ``base_url`` fails validation (missing
    ``http(s)://`` scheme, or absent from ``GLPI_BASE_URL_ALLOWLIST``) —
    ALWAYS raised in :class:`GlpiClient`'s constructor, before any HTTP
    request is attempted (Threat Matrix, anti-SSRF)."""


def _validate_base_url(base_url: str, settings: Settings) -> None:
    scheme = urlsplit(base_url).scheme
    if scheme not in ("http", "https"):
        raise GlpiConfigError(
            f"base_url debe usar http o https, recibido: {base_url!r}"
        )
    if base_url not in settings.GLPI_BASE_URL_ALLOWLIST:
        raise GlpiConfigError(
            f"base_url no está en GLPI_BASE_URL_ALLOWLIST: {base_url!r}"
        )


def _parse_content_range_total(header: str | None) -> int | None:
    """Parse the ``total`` half of a GLPI ``Content-Range: a-b/total``
    response header. Returns ``None`` when the header is absent or
    malformed (e.g. GLPI's ``*`` "unknown total" form) — pagination then
    falls back to stopping on an empty page instead."""

    if header is None:
        return None
    _, _, total_str = header.partition("/")
    try:
        return int(total_str)
    except ValueError:
        return None


class GlpiClient:
    """Thin async wrapper over GLPI's ``apirest.php`` with an injectable
    transport. Holds NO session state across calls (Lote 5's ``session.py``
    owns the Redis-cached ``session_token`` lifecycle) — every method here
    takes the caller's current ``session_token``/``app_token`` explicitly.
    """

    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        settings: Settings = default_settings,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        _validate_base_url(base_url, settings)
        self._settings = settings
        self._sleep = sleep
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=settings.GLPI_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def _retry_5xx(
        self, request: Callable[[], Awaitable[httpx.Response]]
    ) -> httpx.Response:
        """Issue ``request()`` with retry-with-backoff on a transient 5xx
        GLPI response — up to ``GLPI_MAX_RETRIES`` extra attempts, sleeping
        ``min(2 ** attempt, GLPI_MAX_BACKOFF_SECONDS)`` seconds between
        attempts (mirrors ``GraphClient``'s 429 backoff loop,
        ``microsoft365/client.py``'s resilience boundary shape). A non-5xx
        response — success or a non-retryable 4xx — is returned/raised on
        the first attempt, exactly like every call site did before."""

        attempt = 0
        while True:
            response = await request()
            if response.status_code < 500:
                response.raise_for_status()
                return response
            attempt += 1
            if attempt > self._settings.GLPI_MAX_RETRIES:
                response.raise_for_status()
            await self._sleep(min(2**attempt, self._settings.GLPI_MAX_BACKOFF_SECONDS))

    async def _get(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
        return await self._retry_5xx(lambda: self._http.get(url, headers=headers))

    async def _post(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
        return await self._retry_5xx(lambda: self._http.post(url, headers=headers))

    async def init_session(self, app_token: str, user_token: str) -> str:
        """``POST {base}/initSession`` — exchanges the connector's App-Token
        + user_token for a ``session_token``. Never logs/echoes either
        token (GA-R6, "sin credenciales ni tokens en el mensaje")."""

        response = await self._post(
            "/initSession",
            headers={
                "App-Token": app_token,
                "Authorization": f"user_token {user_token}",
            },
        )
        payload: dict[str, Any] = response.json()
        return str(payload["session_token"])

    async def kill_session(self, session_token: str, app_token: str) -> None:
        """``GET {base}/killSession`` — invalidates ``session_token`` on the
        GLPI server side."""

        await self._get(
            "/killSession",
            headers={"Session-Token": session_token, "App-Token": app_token},
        )

    async def list_tickets(
        self,
        session_token: str,
        app_token: str,
        *,
        range_start: int = 0,
        range_end: int = 99,
    ) -> list[dict[str, Any]]:
        """``GET {base}/Ticket``, paginating via the ``Range`` header in
        ``GLPI_PAGE_SIZE``-sized chunks from ``range_start`` until EITHER
        ``range_end`` (the caller's own overall upper bound) or the
        server's own ``Content-Range`` total is reached — whichever comes
        first. Bounded additionally by ``GLPI_MAX_PAGES`` regardless of the
        requested range, so a misbehaving server can never trap this in an
        unbounded loop.
        """

        items: list[dict[str, Any]] = []
        start = range_start
        page_size = self._settings.GLPI_PAGE_SIZE
        pages = 0

        while start <= range_end and pages < self._settings.GLPI_MAX_PAGES:
            end = min(start + page_size - 1, range_end)
            response = await self._get(
                "/Ticket",
                headers={
                    "Session-Token": session_token,
                    "App-Token": app_token,
                    "Range": f"{start}-{end}",
                },
            )
            page_items = response.json()
            page_items = page_items if isinstance(page_items, list) else []
            items.extend(page_items)
            pages += 1

            if not page_items:
                break

            total = _parse_content_range_total(response.headers.get("Content-Range"))
            start = end + 1
            if total is not None and start >= total:
                break

        return items

    async def get_ticket_users(
        self, ticket_id: str, session_token: str, app_token: str
    ) -> list[dict[str, Any]]:
        """``GET {base}/Ticket/{id}/Ticket_User`` -> ``[{users_id, type}, ...]``
        — ``type``: 1=solicitante, 2=ASIGNADO, 3=observador (mapper.py/
        adapter.py resolve which role each entry plays)."""

        response = await self._get(
            f"/Ticket/{ticket_id}/Ticket_User",
            headers={"Session-Token": session_token, "App-Token": app_token},
        )
        payload = response.json()
        return payload if isinstance(payload, list) else []

    async def get_user(
        self, user_id: str, session_token: str, app_token: str
    ) -> dict[str, Any]:
        """``GET {base}/User/{id}`` -> ``{id, name, realname, firstname,
        registration_number, ...}``."""

        response = await self._get(
            f"/User/{user_id}",
            headers={"Session-Token": session_token, "App-Token": app_token},
        )
        payload: dict[str, Any] = response.json()
        return payload

    async def get_user_email(
        self, user_id: str, session_token: str, app_token: str
    ) -> list[dict[str, Any]]:
        """``GET {base}/User/{id}/UserEmail`` -> ``[{email, is_default}, ...]``."""

        response = await self._get(
            f"/User/{user_id}/UserEmail",
            headers={"Session-Token": session_token, "App-Token": app_token},
        )
        payload = response.json()
        return payload if isinstance(payload, list) else []

    async def aclose(self) -> None:
        """Release the underlying ``httpx.AsyncClient``'s connections."""

        await self._http.aclose()
