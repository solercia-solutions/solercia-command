"""Read-only Jira Cloud provider port for the bulk organization feed.

Only ``GET`` requests are ever issued (``/rest/api/3/search/jql`` is read via
``GET`` too), so this client is structurally unable to create, edit,
transition or comment anything in Jira. Credentials travel only inside the
``httpx`` Basic-auth object: they are never logged, never part of an error
message and never written to a snapshot.

Resilience: ``429``/``503`` honour ``Retry-After`` (bounded), other ``5xx``
retry with a short backoff, and every listing paginates until the server says
it is the last page (``isLast``/``nextPageToken``/``startAt`` + ``total``),
with a hard page ceiling as a guard against a misbehaving server.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger("solercia.jira_import.client")

ALLOWED_HOST_SUFFIX = ".atlassian.net"
_MAX_PAGES = 2_000
_RETRYABLE = frozenset({429, 502, 503, 504})


class JiraReadError(RuntimeError):
    """A Jira request failed in a non-retryable way (status + path only)."""

    def __init__(self, status_code: int, path: str) -> None:
        super().__init__(f"Jira respondió {status_code} para {path}")
        self.status_code = status_code
        self.path = path


def validate_base_url(base_url: str) -> str:
    """Return the normalized base URL or raise ``ValueError`` (anti-SSRF)."""

    parts = urlsplit(base_url.strip())
    if parts.scheme != "https" or not parts.netloc.endswith(ALLOWED_HOST_SUFFIX):
        raise ValueError("La URL de Jira debe ser https://<sitio>.atlassian.net")
    return f"https://{parts.netloc}"


class JiraReadClient:
    """Thin async GET-only wrapper over Jira Cloud REST v3 and Agile 1.0."""

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_retries: int = 8,
        max_backoff_seconds: float = 60.0,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._sleep = sleep
        self._max_retries = max_retries
        self._max_backoff = max_backoff_seconds
        self.requests_made = 0
        self._http = httpx.AsyncClient(
            base_url=validate_base_url(base_url),
            auth=httpx.BasicAuth(email, api_token),
            timeout=timeout_seconds,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    async def __aenter__(self) -> "JiraReadClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        """``GET path`` and return its decoded JSON body."""

        attempt = 0
        while True:
            try:
                response = await self._http.get(path, params=params)
            except httpx.TransportError:
                attempt += 1
                if attempt > self._max_retries:
                    raise
                await self._sleep(min(2.0**attempt, self._max_backoff))
                continue
            self.requests_made += 1
            if response.status_code in _RETRYABLE:
                attempt += 1
                if attempt > self._max_retries:
                    raise JiraReadError(response.status_code, path)
                await self._sleep(self._retry_after(response, attempt))
                continue
            if response.status_code >= 400:
                logger.warning("Jira respondió %s para %s", response.status_code, path)
                raise JiraReadError(response.status_code, path)
            return response.json()

    def _retry_after(self, response: httpx.Response, attempt: int) -> float:
        header = response.headers.get("Retry-After")
        try:
            seconds = float(header) if header is not None else 2.0**attempt
        except ValueError:
            seconds = 2.0**attempt
        return max(0.0, min(seconds, self._max_backoff))

    async def paginate_values(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        page_size: int = 50,
        values_key: str = "values",
    ) -> list[dict[str, Any]]:
        """Follow ``startAt`` pagination of ``{values, isLast, total}`` pages."""

        items: list[dict[str, Any]] = []
        start_at = 0
        for _ in range(_MAX_PAGES):
            page = await self.get(
                path, {**(params or {}), "startAt": start_at, "maxResults": page_size}
            )
            values = page.get(values_key) or []
            items.extend(values)
            start_at += len(values)
            total = page.get("total")
            if (
                not values
                or page.get("isLast") is True
                or (isinstance(total, int) and start_at >= total)
            ):
                break
        return items

    async def paginate_list(
        self, path: str, params: Mapping[str, Any] | None = None, *, page_size: int = 1000
    ) -> list[dict[str, Any]]:
        """Follow ``startAt`` pagination of endpoints answering a bare list."""

        items: list[dict[str, Any]] = []
        start_at = 0
        for _ in range(_MAX_PAGES):
            page = await self.get(
                path, {**(params or {}), "startAt": start_at, "maxResults": page_size}
            )
            if not isinstance(page, list) or not page:
                break
            items.extend(page)
            start_at += len(page)
        return items

    async def search_jql(
        self, jql: str, fields: list[str], *, page_size: int = 100, expand: str | None = None
    ) -> list[dict[str, Any]]:
        """Every issue matching ``jql`` via ``GET /rest/api/3/search/jql``."""

        items: list[dict[str, Any]] = []
        token: str | None = None
        for _ in range(_MAX_PAGES):
            params: dict[str, Any] = {
                "jql": jql,
                "fields": ",".join(fields),
                "maxResults": page_size,
            }
            if expand:
                params["expand"] = expand
            if token:
                params["nextPageToken"] = token
            page = await self.get("/rest/api/3/search/jql", params)
            items.extend(page.get("issues") or [])
            token = page.get("nextPageToken")
            if page.get("isLast", True) or not token:
                break
        return items
