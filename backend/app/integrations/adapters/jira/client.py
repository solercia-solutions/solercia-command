"""Jira Cloud REST API v3 HTTP client (change 18-adapter-jira, design.md
"Cliente Jira base"). Thin async wrapper over HTTP Basic auth
(``email:api_token``), ``GET /rest/api/3/field`` custom-field resolution
and ``GET /rest/api/3/search/jql``'s ``nextPageToken`` pagination —
every other module (``adapter.py``) builds requests through this ONE class
so the anti-SSRF boundary, 429 backoff and 401/4xx/5xx translation live in
a single place.

The transport is injectable (``transport=httpx.MockTransport(...)``) so the
test suite never touches the real network (design.md "TDD estricto con
httpx.MockTransport").

Unlike M365/Google (a single, fixed, ``https://``-only provider host), a
Jira Cloud site's ``base_url`` is per-connector/per-tenant and effectively
unbounded (``https://<site>.atlassian.net``) — the anti-SSRF boundary here
is a SUFFIX check (``JIRA_BASE_URL_ALLOWED_SUFFIX``) instead of GLPI's
closed allowlist: :class:`JiraConfigError` is raised in the constructor,
BEFORE any request is ever attempted (Threat Matrix, "Anti-SSRF").
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.jira import errors

logger = logging.getLogger("solercia.jira.client")

_MYSELF_PATH = "/rest/api/3/myself"
_FIELD_PATH = "/rest/api/3/field"
_SEARCH_PATH = "/rest/api/3/search/jql"

# Body preview cap for the 4xx/5xx warning log (never dump a large Jira
# error payload, and NEVER the Authorization header, into the logs).
_LOGGED_BODY_PREVIEW_CHARS = 200


class JiraConfigError(ValueError):
    """Raised when a Jira connector's ``base_url`` fails validation (not
    ``https://``, or its host is outside ``JIRA_BASE_URL_ALLOWED_SUFFIX``)
    — ALWAYS raised in :class:`JiraClient`'s constructor, before any HTTP
    request is attempted (Threat Matrix, anti-SSRF)."""


def _validate_base_url(base_url: str, settings: Settings) -> None:
    parts = urlsplit(base_url)
    if parts.scheme != "https":
        raise JiraConfigError(f"base_url debe usar https, recibido: {base_url!r}")
    if not parts.netloc.endswith(settings.JIRA_BASE_URL_ALLOWED_SUFFIX):
        raise JiraConfigError(
            f"base_url debe ser un sitio {settings.JIRA_BASE_URL_ALLOWED_SUFFIX}, "
            f"recibido: {base_url!r}"
        )


def _find_field_id(fields_json: Sequence[Mapping[str, Any]], target_name: str) -> str | None:
    target = target_name.strip().lower()
    for field in fields_json:
        if str(field.get("name", "")).strip().lower() == target:
            field_id = field.get("id")
            return str(field_id) if field_id is not None else None
    return None


def resolve_field_ids(
    fields_json: Sequence[Mapping[str, Any]],
    *,
    story_points_override: str | None = None,
    sprint_field_override: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve the ``story_points``/``sprint`` custom field ids from
    ``GET /field``'s response, by NAME ("Story Points"/"Sprint") — an
    explicit override wins over the by-name lookup (specs/jira-import/
    spec.md "Override cuando el nombre no calza"). Neither field being
    found resolves to ``None`` (specs/jira-import/spec.md "custom field
    ausente -> None en el reporte"), never raises.
    """

    story_points_id = story_points_override or _find_field_id(fields_json, "Story Points")
    sprint_id = sprint_field_override or _find_field_id(fields_json, "Sprint")
    return story_points_id, sprint_id


class JiraClient:
    """Thin async wrapper over Jira Cloud's REST API v3 with an injectable
    transport and an injectable ``sleep`` (429 backoff never waits for real
    in tests)."""

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        settings: Settings = default_settings,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        _validate_base_url(base_url, settings)
        self._settings = settings
        self._sleep = sleep
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            auth=httpx.BasicAuth(email, api_token),
            timeout=settings.JIRA_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def get_myself(self) -> dict[str, Any]:
        """``GET /rest/api/3/myself`` — validates the credentials and
        returns the authenticated account's profile."""

        response = await self._get(_MYSELF_PATH, params=None)
        payload: dict[str, Any] = response.json()
        return payload

    async def get_fields(self) -> list[dict[str, Any]]:
        """``GET /rest/api/3/field`` — every field Jira knows about, used
        to resolve the story points/sprint custom field ids by name."""

        response = await self._get(_FIELD_PATH, params=None)
        payload = response.json()
        return payload if isinstance(payload, list) else []

    async def search_page(
        self,
        jql: str,
        fields: Sequence[str],
        *,
        next_page_token: str | None = None,
    ) -> dict[str, Any]:
        """One page of ``GET /rest/api/3/search/jql``."""

        params: dict[str, str] = {
            "jql": jql,
            "fields": ",".join(fields),
            "maxResults": str(self._settings.JIRA_PAGE_SIZE),
        }
        if next_page_token is not None:
            params["nextPageToken"] = next_page_token
        response = await self._get(_SEARCH_PATH, params=params)
        payload: dict[str, Any] = response.json()
        return payload

    async def list_issues(
        self, jql: str, fields: Sequence[str], *, since: Any = None
    ) -> list[dict[str, Any]]:
        """Follow ``nextPageToken`` until ``isLast=true`` or
        ``JIRA_MAX_PAGES`` is reached, whichever comes first — a
        misbehaving server can never trap this in an unbounded loop.

        specs/jira-import/spec.md "Reintentos agotados": a
        :class:`~app.integrations.adapters.jira.errors.JiraRateLimited`
        raised mid-pagination is re-raised carrying every issue already
        collected from PREVIOUS pages via ``partial_issues`` — nothing
        already extracted is silently discarded.
        """

        effective_jql = jql
        if since is not None:
            since_str = since.strftime("%Y-%m-%d %H:%M")
            effective_jql = f'({jql}) AND updated >= "{since_str}"'

        items: list[dict[str, Any]] = []
        next_token: str | None = None
        pages = 0

        while pages < self._settings.JIRA_MAX_PAGES:
            try:
                page = await self.search_page(
                    effective_jql, fields, next_page_token=next_token
                )
            except errors.JiraRateLimited as exc:
                exc.partial_issues = list(items)
                raise

            page_issues = page.get("issues")
            items.extend(page_issues if isinstance(page_issues, list) else [])
            pages += 1

            if page.get("isLast", True):
                break
            next_token = page.get("nextPageToken")
            if next_token is None:
                break

        return items

    async def _get(self, url: str, *, params: Mapping[str, str] | None) -> httpx.Response:
        """GET ``url`` with the resilience boundary applied: a bounded
        ``Retry-After`` backoff on repeated ``429``, and a ``401`` /
        other-``4xx`` / ``5xx`` mapping so every caller gets the SAME
        controlled-error contract."""

        attempt = 0
        while True:
            try:
                response = await self._http.get(url, params=params)
            except httpx.TimeoutException as exc:
                raise errors.JiraUnavailable() from exc
            except httpx.RequestError as exc:
                raise errors.JiraUnavailable() from exc

            if response.status_code == 429:
                attempt += 1
                if attempt > self._settings.JIRA_MAX_RETRIES:
                    raise errors.JiraRateLimited()
                await self._sleep(self._retry_after_seconds(response))
                continue

            if response.status_code == 401:
                raise errors.JiraAuthError()

            if response.status_code >= 400:
                self._log_error_response(response)
                if response.status_code >= 500:
                    raise errors.JiraUnavailable()  # 5xx: RETRYABLE
                # Remaining 4xx (400/403/404/409...): the request itself
                # is rejected/invalid, never retryable as-is.
                raise errors.JiraRequestFailed()

            return response

    def _retry_after_seconds(self, response: httpx.Response) -> float:
        header = response.headers.get("Retry-After")
        seconds = 1.0
        if header is not None:
            try:
                seconds = float(header)
            except ValueError:
                seconds = 1.0
        # Clamp: an abusive `Retry-After` never sleeps longer than
        # `JIRA_MAX_BACKOFF_SECONDS`.
        return min(seconds, self._settings.JIRA_MAX_BACKOFF_SECONDS)

    @staticmethod
    def _log_error_response(response: httpx.Response) -> None:
        """Log a 4xx/5xx status + truncated body — NEVER the request's
        ``Authorization`` header/credentials (only ``response.text`` is
        read here)."""

        body_preview = response.text[:_LOGGED_BODY_PREVIEW_CHARS]
        logger.warning(
            "Jira respondió %s para %s: %s",
            response.status_code,
            response.request.url if response.request else "?",
            body_preview,
        )

    async def aclose(self) -> None:
        """Release the underlying ``httpx.AsyncClient``'s connections."""

        await self._http.aclose()
