"""GitLab REST API v4 HTTP client (read-only).

Thin async wrapper over ``PRIVATE-TOKEN`` auth. Every GitLab call goes
through this one class, so the anti-SSRF boundary, bounded pagination, the
``429`` backoff and the 401/4xx/5xx translation live in a single place
(same shape as ``adapters/jira/client.py``).

Anti-SSRF: ``base_url`` must be ``https`` and its host must EXACTLY match
one entry of ``GITLAB_BASE_URL_ALLOWLIST`` (comma-separated). The check runs
in the constructor, before any request; URLs carrying user info are refused
so ``https://gitlab.com@evil`` style tricks never reach the network.

The transport is injectable (``httpx.MockTransport`` in tests) and so is
``sleep`` (backoff never waits for real in tests). Only ``GET`` exists here:
the integration never writes back to GitLab.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.gitlab import errors

logger = logging.getLogger("solercia.gitlab.client")

_API_PREFIX = "/api/v4"
_LOGGED_BODY_PREVIEW_CHARS = 200


def allowed_hosts(settings: Settings) -> frozenset[str]:
    """Parse ``GITLAB_BASE_URL_ALLOWLIST`` into a set of lowercase hosts."""

    return frozenset(
        host.strip().lower()
        for host in settings.GITLAB_BASE_URL_ALLOWLIST.split(",")
        if host.strip()
    )


def normalize_base_url(base_url: str, settings: Settings) -> str:
    """Validate ``base_url`` (https + allowlisted host, no user info) and
    return it without a trailing slash. Raises ``GitlabConfigInvalid``."""

    candidate = base_url.strip()
    # httpx rejects these later with InvalidURL (an unhandled 500); refuse them
    # here, before any request, with the same controlled error.
    if any(char.isspace() or not char.isprintable() for char in candidate):
        raise errors.GitlabConfigInvalid()
    parts = urlsplit(candidate)
    if parts.scheme != "https":
        raise errors.GitlabConfigInvalid("La dirección de GitLab debe usar https.")
    host = (parts.hostname or "").lower()
    if parts.username or parts.password or not host or host not in allowed_hosts(settings):
        raise errors.GitlabConfigInvalid()
    return base_url.strip().rstrip("/")


def encode_project_path(path_with_namespace: str) -> str:
    """URL-encode ``group/sub/repo`` as GitLab's ``:id`` path segment."""

    return quote(path_with_namespace, safe="")


class GitlabClient:
    """Async, read-only GitLab REST v4 client."""

    def __init__(
        self,
        base_url: str,
        access_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        settings: Settings = default_settings,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        normalized = normalize_base_url(base_url, settings)
        self._settings = settings
        self._sleep = sleep
        self._http = httpx.AsyncClient(
            base_url=f"{normalized}{_API_PREFIX}",
            headers={"PRIVATE-TOKEN": access_token},
            timeout=settings.GITLAB_TIMEOUT_SECONDS,
            transport=transport,
            follow_redirects=False,
        )

    async def get_user(self) -> dict[str, Any]:
        """``GET /user`` — the token's owner (bot user for group/project tokens)."""

        return await self._get_json_object("/user")

    async def get_token_self(self) -> dict[str, Any]:
        """``GET /personal_access_tokens/self`` — the token's own scopes."""

        return await self._get_json_object("/personal_access_tokens/self")

    async def get_project(self, path_with_namespace: str) -> dict[str, Any]:
        """``GET /projects/:id`` for a ``group/repo`` path."""

        return await self._get_json_object(f"/projects/{encode_project_path(path_with_namespace)}")

    async def list_member_projects(self) -> list[dict[str, Any]]:
        """``GET /projects?membership=true&simple=true`` (bounded pages)."""

        return await self._paginate(
            "/projects",
            {"membership": "true", "simple": "true", "order_by": "path", "sort": "asc"},
        )

    async def list_merge_requests(
        self, path_with_namespace: str, search: str
    ) -> list[dict[str, Any]]:
        """Merge requests of a project whose title matches ``search``."""

        return await self._paginate(
            f"/projects/{encode_project_path(path_with_namespace)}/merge_requests",
            {"search": search, "in": "title", "state": "all", "scope": "all"},
        )

    async def list_commits(self, path_with_namespace: str) -> list[dict[str, Any]]:
        """Most recent commits across every branch (bounded pages).

        GitLab's commit list has no message filter on every edition, so the
        caller filters by message; the page bound caps how far back it looks.
        """

        return await self._paginate(
            f"/projects/{encode_project_path(path_with_namespace)}/repository/commits",
            {"all": "true"},
        )

    async def _paginate(self, path: str, params: Mapping[str, str]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        for _ in range(self._settings.GITLAB_MAX_PAGES):
            page_params = {
                **params,
                "per_page": str(self._settings.GITLAB_PAGE_SIZE),
                "page": str(page),
            }
            response = await self._get(path, params=page_params)
            payload = response.json()
            if isinstance(payload, list):
                items.extend(item for item in payload if isinstance(item, dict))
            next_page = response.headers.get("X-Next-Page", "").strip()
            if not next_page.isdigit():
                break
            page = int(next_page)
        return items

    async def _get_json_object(self, path: str) -> dict[str, Any]:
        response = await self._get(path, params=None)
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def _get(self, path: str, *, params: Mapping[str, str] | None) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = await self._http.get(path, params=params)
            except httpx.RequestError as exc:
                raise errors.GitlabUnavailable() from exc

            if response.status_code == 429:
                attempt += 1
                if attempt > self._settings.GITLAB_MAX_RETRIES:
                    raise errors.GitlabRateLimited()
                await self._sleep(self._retry_after_seconds(response))
                continue
            if response.status_code == 401:
                raise errors.GitlabAuthError()
            if response.status_code >= 400:
                self._log_error_response(response)
                if response.status_code >= 500:
                    raise errors.GitlabUnavailable()
                if response.status_code == 404:
                    raise errors.GitlabNotFound()
                raise errors.GitlabRequestFailed()
            if response.status_code >= 300:
                # Redirects are never followed: a 3xx could point outside the
                # allowlisted host.
                raise errors.GitlabRequestFailed()
            return response

    def _retry_after_seconds(self, response: httpx.Response) -> float:
        seconds = 1.0
        header = response.headers.get("Retry-After")
        if header is not None:
            try:
                seconds = float(header)
            except ValueError:
                seconds = 1.0
        return min(max(seconds, 0.0), self._settings.GITLAB_MAX_BACKOFF_SECONDS)

    @staticmethod
    def _log_error_response(response: httpx.Response) -> None:
        """Status + truncated body only — never the ``PRIVATE-TOKEN`` header."""

        logger.warning(
            "GitLab respondió %s para %s: %s",
            response.status_code,
            response.request.url.path if response.request else "?",
            response.text[:_LOGGED_BODY_PREVIEW_CHARS],
        )

    async def aclose(self) -> None:
        await self._http.aclose()
