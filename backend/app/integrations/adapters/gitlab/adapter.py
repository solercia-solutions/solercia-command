"""``GitlabAdapter`` — read-only GitLab integration, ``credential_kind=api_token``.

The handshake validates ``base_url`` + ``access_token`` against
``GET /api/v4/user`` and ``GET /api/v4/personal_access_tokens/self`` and
only accepts read-only tokens: ``read_api`` is required and any scope outside
:data:`ALLOWED_SCOPES` is rejected, so such a token is never persisted (the
connectors service encrypts only after ``connect`` returns).

Beyond the generic handshake the adapter exposes GitLab-specific read
methods (``list_repositories``, ``get_repository``, ``find_activity``) that
the ``gitlab_integration`` module calls directly, the same way the Jira
adapter exposes ``import_issues``. It declares no core capability port: a
repository's development activity has no generic port yet.
"""

import asyncio
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.gitlab import errors
from app.integrations.adapters.gitlab.client import GitlabClient
from app.integrations.adapters.gitlab.dtos import (
    GitlabCommit,
    GitlabMergeRequest,
    GitlabRepository,
)
from app.integrations.dtos import AccountRef
from app.integrations.ports import (
    ApiTokenHandshake,
    Capability,
    CredentialKind,
    OAuthHandshake,
)

REQUIRED_SCOPE = "read_api"
# Allowlist, never a denylist: any scope GitLab adds later is rejected until it
# is reviewed and listed here as read-only.
ALLOWED_SCOPES: frozenset[str] = frozenset(
    {
        REQUIRED_SCOPE,
        "read_user",
        "read_repository",
        "read_registry",
        "read_virtual_registry",
        "read_observability",
        "openid",
        "profile",
        "email",
    }
)

_EPOCH = datetime.min.replace(tzinfo=UTC)

SleepFn = Callable[[float], Awaitable[None]]


def mentions_task_key(text: str | None, task_key: str) -> bool:
    """True when ``text`` mentions ``task_key`` as a whole token.

    ``CMD-12`` matches ``"CMD-12: fix"`` or ``"[cmd-12]"`` but never
    ``CMD-123`` nor ``XCMD-12`` (case-insensitive, like Jira smart commits).
    """

    if not text or not task_key:
        return False
    pattern = rf"(?<![A-Za-z0-9]){re.escape(task_key)}(?![A-Za-z0-9])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _credentials(raw: Mapping[str, str]) -> tuple[str, str]:
    base_url = (raw.get("base_url") or "").strip()
    access_token = (raw.get("access_token") or "").strip()
    if not base_url or not access_token:
        raise errors.GitlabCredentialsIncomplete()
    return base_url, access_token


class _GitlabApiTokenHandshake:
    """Validates a token and its scopes; never persists anything."""

    def __init__(self, adapter: "GitlabAdapter") -> None:
        self._adapter = adapter

    async def connect(self, raw: Mapping[str, str]) -> AccountRef:
        base_url, access_token = _credentials(raw)
        async with self._adapter.client(base_url, access_token) as client:
            user = await client.get_user()
            try:
                token = await client.get_token_self()
            except errors.GitlabNotFound as exc:
                # Old GitLab versions and some token types cannot describe
                # themselves: without the scopes the token cannot be vetted.
                raise errors.GitlabTokenNotInspectable() from exc

        if token.get("active") is False or token.get("revoked") is True:
            raise errors.GitlabAuthError()
        scopes = {str(scope) for scope in token.get("scopes") or []}
        forbidden = scopes - ALLOWED_SCOPES
        if forbidden:
            raise errors.GitlabTokenScopeNotAllowed(forbidden)
        if REQUIRED_SCOPE not in scopes:
            raise errors.GitlabTokenScopeMissing()

        user_id = user.get("id")
        if user_id is None:
            raise errors.GitlabAuthError()
        name = user.get("name") or "Cuenta de GitLab"
        username = user.get("username")
        display_name = f"{name} (@{username})" if username else str(name)
        return AccountRef(external_account_id=f"gitlab-{user_id}", display_name=display_name)


class _ClientContext:
    """``async with`` wrapper that always closes the underlying client."""

    def __init__(self, factory: Callable[[], GitlabClient]) -> None:
        self._factory = factory
        self._client: GitlabClient | None = None

    async def __aenter__(self) -> GitlabClient:
        self._client = self._factory()
        return self._client

    async def __aexit__(self, *_exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()


class GitlabAdapter:
    """GitLab adapter — read-only, ``credential_kind=api_token``."""

    provider = "gitlab"
    capabilities: frozenset[Capability] = frozenset()
    credential_kind = CredentialKind.api_token
    credential_kinds = frozenset({CredentialKind.api_token})

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._sleep = sleep
        self.oauth: OAuthHandshake | None = None
        self.api_token: ApiTokenHandshake | None = _GitlabApiTokenHandshake(self)

    def port_for(self, capability: Capability) -> object | None:
        return None

    def client(self, base_url: str, access_token: str) -> _ClientContext:
        """Build a client bound to this adapter's settings and transport.

        The constructor validates ``base_url`` first, so an invalid host
        raises before any request is attempted."""

        return _ClientContext(
            lambda: GitlabClient(
                base_url,
                access_token,
                transport=self._transport,
                settings=self._settings,
                sleep=self._sleep,
            )
        )

    async def list_repositories(self, raw: Mapping[str, str]) -> list[GitlabRepository]:
        """Projects the token is a member of, ordered by path."""

        base_url, access_token = _credentials(raw)
        async with self.client(base_url, access_token) as client:
            projects = await client.list_member_projects()
        return [
            GitlabRepository(
                path_with_namespace=str(project["path_with_namespace"]),
                name=str(project.get("name") or project["path_with_namespace"]),
                web_url=project.get("web_url"),
            )
            for project in projects
            if project.get("path_with_namespace")
        ]

    async def get_repository(
        self, raw: Mapping[str, str], path_with_namespace: str
    ) -> GitlabRepository:
        """One project by path; ``GitlabNotFound`` when the token cannot see it."""

        base_url, access_token = _credentials(raw)
        async with self.client(base_url, access_token) as client:
            project = await client.get_project(path_with_namespace)
        path = str(project.get("path_with_namespace") or path_with_namespace)
        return GitlabRepository(
            path_with_namespace=path,
            name=str(project.get("name") or path),
            web_url=project.get("web_url"),
        )

    async def find_activity(
        self, raw: Mapping[str, str], repositories: Iterable[str], task_key: str
    ) -> tuple[list[GitlabMergeRequest], list[GitlabCommit]]:
        """Merge requests and commits in ``repositories`` that mention
        ``task_key`` as a whole token (title for MRs, message for commits)."""

        base_url, access_token = _credentials(raw)
        merge_requests: list[GitlabMergeRequest] = []
        commits: list[GitlabCommit] = []
        async with self.client(base_url, access_token) as client:
            for repository in repositories:
                for mr in await client.list_merge_requests(repository, task_key):
                    if not mentions_task_key(mr.get("title"), task_key):
                        continue
                    author = mr.get("author") or {}
                    merge_requests.append(
                        GitlabMergeRequest(
                            repository=repository,
                            iid=int(mr.get("iid") or 0),
                            title=str(mr.get("title") or ""),
                            state=str(mr.get("state") or ""),
                            author=author.get("name") if isinstance(author, dict) else None,
                            source_branch=mr.get("source_branch"),
                            updated_at=_parse_datetime(mr.get("updated_at")),
                            web_url=mr.get("web_url"),
                        )
                    )
                for commit in await client.list_commits(repository):
                    if not mentions_task_key(commit.get("message"), task_key):
                        continue
                    commits.append(
                        GitlabCommit(
                            repository=repository,
                            short_id=str(commit.get("short_id") or ""),
                            title=str(commit.get("title") or ""),
                            author_name=commit.get("author_name"),
                            authored_at=_parse_datetime(commit.get("authored_date")),
                            web_url=commit.get("web_url"),
                        )
                    )

        merge_requests.sort(key=lambda mr: mr.updated_at or _EPOCH, reverse=True)
        commits.sort(key=lambda c: c.authored_at or _EPOCH, reverse=True)
        return merge_requests, commits


__all__ = ["GitlabAdapter", "ALLOWED_SCOPES", "REQUIRED_SCOPE", "mentions_task_key"]
