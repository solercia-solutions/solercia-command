"""RED tests for the Jira adapter's HTTP client (change 18-adapter-jira,
specs/jira-import/spec.md). Every test runs against `httpx.MockTransport`
fixtures under `tests/fixtures/jira/` — ZERO real network in CI (design.md
"TDD estricto con httpx.MockTransport").
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from app.config import Settings

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "jira"
_ALLOWED_BASE_URL = "https://acme.atlassian.net"


def _load_fixture(name: str) -> dict | list:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]


async def _no_sleep(_seconds: float) -> None:
    """Injected `sleep` — the 429 backoff never actually waits in tests."""


# ---------------------------------------------------------------------------
# Anti-SSRF: base_url validation happens BEFORE any request
# ---------------------------------------------------------------------------


class TestJiraClientBaseUrl:
    def test_rejects_base_url_without_https_before_any_request(self) -> None:
        from app.integrations.adapters.jira.client import JiraClient, JiraConfigError

        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        with pytest.raises(JiraConfigError):
            JiraClient(
                "http://acme.atlassian.net",
                "user@acme.com",
                "token-x",
                transport=httpx.MockTransport(handler),
                settings=_settings(),
            )
        assert calls == 0

    def test_rejects_host_outside_atlassian_net_before_any_request(self) -> None:
        """Threat Matrix (anti-SSRF): a `base_url` outside `*.atlassian.net`
        is rejected in the constructor — zero HTTP calls."""

        from app.integrations.adapters.jira.client import JiraClient, JiraConfigError

        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        with pytest.raises(JiraConfigError):
            JiraClient(
                "https://169.254.169.254",
                "user@acme.com",
                "token-x",
                transport=httpx.MockTransport(handler),
                settings=_settings(),
            )
        assert calls == 0

    def test_accepts_a_valid_atlassian_net_https_base_url(self) -> None:
        from app.integrations.adapters.jira.client import JiraClient

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={})

        client = JiraClient(
            _ALLOWED_BASE_URL,
            "user@acme.com",
            "token-x",
            transport=httpx.MockTransport(handler),
            settings=_settings(),
        )
        assert client is not None


# ---------------------------------------------------------------------------
# Basic auth + /myself
# ---------------------------------------------------------------------------


class TestJiraClientMyself:
    @pytest.mark.asyncio
    async def test_get_myself_sends_basic_auth_and_returns_the_profile(self) -> None:
        payload = _load_fixture("myself.json")
        seen_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal seen_request
            seen_request = request
            return httpx.Response(200, json=payload)

        from app.integrations.adapters.jira.client import JiraClient

        client = JiraClient(
            _ALLOWED_BASE_URL,
            "user@acme.com",
            "secret-token",
            transport=httpx.MockTransport(handler),
            settings=_settings(),
        )

        result = await client.get_myself()

        assert result == payload
        assert seen_request is not None
        auth_header = seen_request.headers.get("Authorization", "")
        assert auth_header.startswith("Basic ")
        await client.aclose()


# ---------------------------------------------------------------------------
# GET /field + resolve_field_ids (pure)
# ---------------------------------------------------------------------------


class TestResolveFieldIds:
    def test_resolves_story_points_and_sprint_by_name(self) -> None:
        from app.integrations.adapters.jira.client import resolve_field_ids

        fields_json = _load_fixture("fields.json")

        story_points_id, sprint_id = resolve_field_ids(fields_json)

        assert story_points_id == "customfield_10032"
        assert sprint_id == "customfield_10020"

    def test_override_wins_when_the_name_does_not_calzar(self) -> None:
        from app.integrations.adapters.jira.client import resolve_field_ids

        fields_json = _load_fixture("fields.json")

        story_points_id, _ = resolve_field_ids(
            fields_json, story_points_override="customfield_99999"
        )

        assert story_points_id == "customfield_99999"

    def test_absent_custom_field_resolves_to_none(self) -> None:
        from app.integrations.adapters.jira.client import resolve_field_ids

        story_points_id, sprint_id = resolve_field_ids([{"id": "summary", "name": "Summary"}])

        assert story_points_id is None
        assert sprint_id is None

    @pytest.mark.asyncio
    async def test_get_fields_returns_the_raw_field_list(self) -> None:
        payload = _load_fixture("fields.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        from app.integrations.adapters.jira.client import JiraClient

        client = JiraClient(
            _ALLOWED_BASE_URL,
            "user@acme.com",
            "secret-token",
            transport=httpx.MockTransport(handler),
            settings=_settings(),
        )

        result = await client.get_fields()

        assert result == payload
        await client.aclose()


# ---------------------------------------------------------------------------
# Pagination — nextPageToken until isLast
# ---------------------------------------------------------------------------


class TestJiraClientPagination:
    @pytest.mark.asyncio
    async def test_list_issues_follows_next_page_token_until_is_last(self) -> None:
        page1 = _load_fixture("search_page1.json")
        page2 = _load_fixture("search_page2.json")
        calls: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            token = request.url.params.get("nextPageToken")
            calls.append(token)
            return httpx.Response(200, json=page2 if token else page1)

        from app.integrations.adapters.jira.client import JiraClient

        client = JiraClient(
            _ALLOWED_BASE_URL,
            "user@acme.com",
            "secret-token",
            transport=httpx.MockTransport(handler),
            settings=_settings(),
        )

        issues = await client.list_issues("project = PROJ", ["summary"])

        assert len(issues) == 3  # 2 from page1 + 1 from page2
        assert calls == [None, "CAEaAggD"]
        await client.aclose()


# ---------------------------------------------------------------------------
# `since` -> effective JQL (`(jql) AND updated >= "YYYY-MM-DD HH:MM"`)
# ---------------------------------------------------------------------------


class TestJiraClientSinceFilter:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("jql", "expected"),
        [
            ("", '() AND updated >= "2024-01-01 08:30"'),
            (
                'project = "PROJ X"',
                '(project = "PROJ X") AND updated >= "2024-01-01 08:30"',
            ),
        ],
    )
    async def test_since_wraps_the_jql_into_a_well_formed_updated_clause(
        self, jql: str, expected: str
    ) -> None:
        page = _load_fixture("search_page2.json")  # isLast=true -> single page
        seen_jql: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_jql.append(request.url.params.get("jql"))
            return httpx.Response(200, json=page)

        from app.integrations.adapters.jira.client import JiraClient

        client = JiraClient(
            _ALLOWED_BASE_URL,
            "user@acme.com",
            "secret-token",
            transport=httpx.MockTransport(handler),
            settings=_settings(),
        )

        await client.list_issues(jql, ["summary"], since=datetime(2024, 1, 1, 8, 30))

        assert seen_jql == [expected]
        await client.aclose()


# ---------------------------------------------------------------------------
# 429 Retry-After — bounded backoff and controlled failure
# ---------------------------------------------------------------------------


class TestJiraClientRateLimit:
    @pytest.mark.asyncio
    async def test_retries_after_429_and_completes_on_the_next_2xx(self) -> None:
        error_payload = _load_fixture("search_429.json")
        page2 = _load_fixture("search_page2.json")  # isLast=true -> a single page
        attempts = 0
        slept: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(
                    429, json=error_payload, headers={"Retry-After": "2"}
                )
            return httpx.Response(200, json=page2)

        async def _record_sleep(seconds: float) -> None:
            slept.append(seconds)

        from app.integrations.adapters.jira.client import JiraClient

        client = JiraClient(
            _ALLOWED_BASE_URL,
            "user@acme.com",
            "secret-token",
            transport=httpx.MockTransport(handler),
            settings=_settings(),
            sleep=_record_sleep,
        )

        issues = await client.list_issues("project = PROJ", ["summary"])

        assert attempts == 2
        assert slept == [2.0]
        assert len(issues) == 1
        await client.aclose()

    @pytest.mark.asyncio
    async def test_retry_after_never_sleeps_past_the_backoff_ceiling(self) -> None:
        error_payload = _load_fixture("search_429.json")
        slept: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json=error_payload, headers={"Retry-After": "3600"})

        async def _record_sleep(seconds: float) -> None:
            slept.append(seconds)

        from app.integrations.adapters.jira import errors
        from app.integrations.adapters.jira.client import JiraClient

        client = JiraClient(
            _ALLOWED_BASE_URL,
            "user@acme.com",
            "secret-token",
            transport=httpx.MockTransport(handler),
            settings=_settings(JIRA_MAX_RETRIES=1, JIRA_MAX_BACKOFF_SECONDS=5.0),
            sleep=_record_sleep,
        )

        with pytest.raises(errors.JiraRateLimited):
            await client.list_issues("project = PROJ", ["summary"])

        assert all(seconds <= 5.0 for seconds in slept)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises_without_losing_previously_fetched_pages(
        self,
    ) -> None:
        """specs/jira-import/spec.md 'Reintentos agotados': page 1 succeeds,
        page 2 gets rate-limited forever — the raised error still carries
        every issue extracted from page 1."""

        page1 = _load_fixture("search_page1.json")
        error_payload = _load_fixture("search_429.json")
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(200, json=page1)
            return httpx.Response(429, json=error_payload, headers={"Retry-After": "0"})

        from app.integrations.adapters.jira import errors
        from app.integrations.adapters.jira.client import JiraClient

        client = JiraClient(
            _ALLOWED_BASE_URL,
            "user@acme.com",
            "secret-token",
            transport=httpx.MockTransport(handler),
            settings=_settings(JIRA_MAX_RETRIES=1),
            sleep=_no_sleep,
        )

        with pytest.raises(errors.JiraRateLimited) as exc_info:
            await client.list_issues("project = PROJ", ["summary"])

        assert len(exc_info.value.partial_issues) == 2  # page 1's two issues survive
        await client.aclose()


# ---------------------------------------------------------------------------
# 401 — controlled error, no secret leak
# ---------------------------------------------------------------------------


class TestJiraClientAuthError:
    @pytest.mark.asyncio
    async def test_401_raises_a_controlled_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"errorMessages": ["Unauthorized"]})

        from app.integrations.adapters.jira import errors
        from app.integrations.adapters.jira.client import JiraClient

        client = JiraClient(
            _ALLOWED_BASE_URL,
            "user@acme.com",
            "very-secret-token",
            transport=httpx.MockTransport(handler),
            settings=_settings(),
        )

        with pytest.raises(errors.JiraAuthError):
            await client.get_myself()
        await client.aclose()

    @pytest.mark.asyncio
    async def test_no_secret_leaks_in_the_exception_text_or_logs(self, caplog) -> None:
        """specs/jira-import/spec.md 'Credencial inválida se rechaza sin
        exponer el secreto': neither the email nor the api_token ever
        appear in `str(exception)` or in any log record."""

        email = "user@acme.com"
        api_token = "SUPER-SECRET-TOKEN-VALUE"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"errorMessages": ["Unauthorized"]})

        from app.integrations.adapters.jira.client import JiraClient

        client = JiraClient(
            _ALLOWED_BASE_URL,
            email,
            api_token,
            transport=httpx.MockTransport(handler),
            settings=_settings(),
        )

        caught: Exception | None = None
        with caplog.at_level(logging.DEBUG):
            try:
                await client.get_myself()
            except Exception as exc:  # noqa: BLE001 - captured for assertion below
                caught = exc

        assert caught is not None
        assert api_token not in str(caught)
        assert email not in str(caught)
        for record in caplog.records:
            assert api_token not in record.getMessage()
            assert email not in record.getMessage()
        await client.aclose()


# ---------------------------------------------------------------------------
# `list_projects` -> `GET /rest/api/3/project/search` (startAt/isLast)
# ---------------------------------------------------------------------------


class TestJiraClientListProjects:
    @pytest.mark.asyncio
    async def test_list_projects_pages_with_start_at_until_is_last(self) -> None:
        pages = {
            0: {
                "values": [{"key": "PROJ", "name": "Proyecto", "id": "1"}],
                "isLast": False,
                "total": 2,
            },
            1: {"values": [{"key": "OPS", "name": "Operaciones", "id": "2"}], "isLast": True},
        }
        seen: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/rest/api/3/project/search"
            start_at = int(request.url.params.get("startAt", "0"))
            seen.append(start_at)
            return httpx.Response(200, json=pages[start_at])

        from app.integrations.adapters.jira.client import JiraClient

        client = JiraClient(
            _ALLOWED_BASE_URL,
            "user@acme.com",
            "secret-token",
            transport=httpx.MockTransport(handler),
            settings=_settings(),
        )

        projects = await client.list_projects()

        assert projects == [
            {"key": "PROJ", "name": "Proyecto"},
            {"key": "OPS", "name": "Operaciones"},
        ]
        assert seen == [0, 1]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_list_projects_is_bounded_by_jira_max_pages(self) -> None:
        """A server that never says ``isLast`` cannot trap the loop."""

        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                200, json={"values": [{"key": f"P{calls}", "name": "x"}], "isLast": False}
            )

        from app.integrations.adapters.jira.client import JiraClient

        client = JiraClient(
            _ALLOWED_BASE_URL,
            "user@acme.com",
            "secret-token",
            transport=httpx.MockTransport(handler),
            settings=_settings(JIRA_MAX_PAGES=3),
        )

        projects = await client.list_projects()

        assert calls == 3
        assert len(projects) == 3
        await client.aclose()

    @pytest.mark.asyncio
    async def test_list_projects_maps_401_to_the_controlled_auth_error(self) -> None:
        from app.integrations.adapters.jira import errors
        from app.integrations.adapters.jira.client import JiraClient

        client = JiraClient(
            _ALLOWED_BASE_URL,
            "user@acme.com",
            "secret-token",
            transport=httpx.MockTransport(lambda request: httpx.Response(401)),
            settings=_settings(),
        )

        with pytest.raises(errors.JiraAuthError):
            await client.list_projects()
        await client.aclose()
