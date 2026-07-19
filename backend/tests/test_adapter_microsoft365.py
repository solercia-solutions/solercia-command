"""RED tests for the `microsoft365` adapter (change 15-adapter-microsoft365,
specs/adapter-microsoft365/spec.md). First REAL provider over the 14's
read-only ports (Microsoft Graph, delegated OAuth/Entra ID).

Every test runs against `httpx.MockTransport` fixtures under
`tests/fixtures/graph/` — ZERO real network in CI (design.md "GraphClient
httpx inyectable"). Classes are grouped by work unit/lote so `pytest -k` can
target a single batch's RED/GREEN cycle:
    TestGraphClientBase        — Lote 1 (paginación + TLS + anti-SSRF)
    TestGraphClientResilience  — Lote 2 (401 refresh + 429 backoff)
    TestOAuthAndRegistry       — Lote 3 (handshake OAuth + registro)
    TestMailPort                — Lote 4
    TestCalendarPort             — Lote 5
    TestPlannerPort               — Lote 6
    TestMeetingNotesPort            — Lote 7
    TestWriteBoundary                — Lote 8
"""

import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.integrations.ports import AccessContext

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "graph"


def _load_fixture(name: str) -> dict:
    """Load a Graph response fixture by filename from `tests/fixtures/graph/`."""

    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _ctx(**overrides) -> AccessContext:
    """Build an `AccessContext` for the adapter's tests, real access token."""

    defaults = {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "scopes": (),
    }
    defaults.update(overrides)
    return AccessContext(**defaults)


def _settings(**overrides) -> Settings:
    """Build a real `Settings` instance with `M365_*` overrides for a test."""

    return Settings(**overrides)


# ---------------------------------------------------------------------------
# Lote 1 — Cliente Graph base: paginación + TLS obligatorio + anti-SSRF
# ---------------------------------------------------------------------------


class TestGraphClientBase:
    def test_rejects_non_https_graph_base_url(self) -> None:
        """M365-Threat-Matrix: TLS obligatorio — `GraphClient` fails fast when
        `M365_GRAPH_BASE_URL` is not `https://`."""

        from app.integrations.adapters.microsoft365.client import GraphClient

        bad_settings = _settings(M365_GRAPH_BASE_URL="http://graph.microsoft.com/v1.0")

        with pytest.raises(ValueError, match="M365_GRAPH_BASE_URL"):
            GraphClient(_ctx(), settings=bad_settings)

    def test_rejects_non_https_login_base_url(self) -> None:
        """Same TLS guard applies to `M365_LOGIN_BASE_URL` (used by oauth.py,
        Lote 3), checked here since both live on the same constructor."""

        from app.integrations.adapters.microsoft365.client import GraphClient

        bad_settings = _settings(
            M365_LOGIN_BASE_URL="http://login.microsoftonline.com"
        )

        with pytest.raises(ValueError, match="M365_LOGIN_BASE_URL"):
            GraphClient(_ctx(), settings=bad_settings)

    @pytest.mark.asyncio
    async def test_paginate_follows_next_link_across_pages(self) -> None:
        """Scenario: Resultados dentro de la ventana, multi-página — two
        fixture pages chained by `@odata.nextLink` are fully aggregated."""

        from app.integrations.adapters.microsoft365.client import GraphClient

        page_1 = _load_fixture("generic_page_1.json")
        page_2 = _load_fixture("generic_page_2.json")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.params.get("$skip") == "2":
                return httpx.Response(200, json=page_2)
            return httpx.Response(200, json=page_1)

        client = GraphClient(_ctx(), transport=httpx.MockTransport(handler))

        items = await client.paginate("/generic", limit=10)

        assert [item["id"] for item in items] == [
            "generic-item-1",
            "generic-item-2",
            "generic-item-3",
        ]

    @pytest.mark.asyncio
    async def test_paginate_single_page_without_next_link_returns_its_items(
        self,
    ) -> None:
        """A response with no `@odata.nextLink` terminates pagination after
        one page — the fixture with a single, un-paginated result set."""

        from app.integrations.adapters.microsoft365.client import GraphClient

        payload = _load_fixture("generic_single_page.json")
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=payload)

        client = GraphClient(_ctx(), transport=httpx.MockTransport(handler))

        items = await client.paginate("/generic", limit=50)

        assert [item["id"] for item in items] == ["generic-solo-item"]
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_paginate_stops_once_limit_is_reached(self) -> None:
        """`limit` is respected even when the first page alone exceeds it —
        no extra page is fetched once enough items are already collected."""

        from app.integrations.adapters.microsoft365.client import GraphClient

        page_1 = _load_fixture("generic_page_1.json")  # 2 items + nextLink
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=page_1)

        client = GraphClient(_ctx(), transport=httpx.MockTransport(handler))

        items = await client.paginate("/generic", limit=1)

        assert [item["id"] for item in items] == ["generic-item-1"]
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_paginate_cuts_off_at_max_pages_without_looping_forever(
        self,
    ) -> None:
        """A Graph response that always returns another `@odata.nextLink`
        (adversarial/misbehaving server) is bounded by `M365_MAX_PAGES` —
        never an infinite loop."""

        from app.integrations.adapters.microsoft365.client import GraphClient

        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(
                200,
                json={
                    "value": [{"id": f"forever-item-{call_count}"}],
                    "@odata.nextLink": (
                        "https://graph.microsoft.com/v1.0/generic?cursor=forever"
                    ),
                },
            )

        settings = _settings(M365_MAX_PAGES=3)
        client = GraphClient(
            _ctx(), transport=httpx.MockTransport(handler), settings=settings
        )

        items = await client.paginate("/generic", limit=1000)

        assert call_count == 3
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_paginate_refuses_to_follow_a_next_link_on_a_foreign_host(
        self,
    ) -> None:
        """Anti-SSRF/host fijo: a `@odata.nextLink` pointing at a host other
        than `M365_GRAPH_BASE_URL` is NEVER requested — the client derives
        every request's host solely from configuration, never from Graph's
        own response body."""

        from app.integrations.adapters.microsoft365.client import (
            GraphClient,
            GraphHostMismatchError,
        )

        requested_hosts: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_hosts.append(request.url.host)
            return httpx.Response(
                200,
                json={
                    "value": [{"id": "legit-item"}],
                    "@odata.nextLink": "https://evil.example.com/v1.0/generic?steal=1",
                },
            )

        client = GraphClient(_ctx(), transport=httpx.MockTransport(handler))

        with pytest.raises(GraphHostMismatchError):
            await client.paginate("/generic", limit=1000)

        assert requested_hosts == ["graph.microsoft.com"]


# ---------------------------------------------------------------------------
# Lote 2 — Cliente Graph resiliencia: 401 refresh + 429 backoff + errores
# ---------------------------------------------------------------------------


async def _noop_sleep(_seconds: float) -> None:
    """Injectable `sleep` that never actually waits — the resilience tests
    exercise the retry LOGIC, not real time (design.md, "sin espera real")."""


class TestGraphClientResilience:
    @pytest.mark.asyncio
    async def test_401_triggers_refresh_once_and_retries_successfully(self) -> None:
        """Scenario: Refresco automático o error controlado — a 401 makes the
        client refresh the token exactly once and retry the SAME request,
        which then succeeds (M365-R3)."""

        from app.integrations.adapters.microsoft365.client import GraphClient
        from app.integrations.dtos import OAuthTokens

        unauthorized = _load_fixture("unauthorized_401.json")
        ok = _load_fixture("ok_after_retry.json")
        seen_tokens: list[str] = []
        refresh_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            seen_tokens.append(request.headers["Authorization"])
            if request.headers["Authorization"] == "Bearer test-access-token":
                return httpx.Response(401, json=unauthorized)
            return httpx.Response(200, json=ok)

        async def refresh(refresh_token: str) -> OAuthTokens:
            nonlocal refresh_calls
            refresh_calls += 1
            assert refresh_token == "test-refresh-token"
            return OAuthTokens(
                external_account_id="oid-123",
                access_token="fresh-access-token",
                refresh_token="fresh-refresh-token",
                expires_at=None,
                scopes=("Mail.Read",),
            )

        sink_calls: list[OAuthTokens] = []

        async def on_tokens_refreshed(tokens: OAuthTokens) -> None:
            sink_calls.append(tokens)

        ctx = _ctx(on_tokens_refreshed=on_tokens_refreshed)
        client = GraphClient(
            ctx, transport=httpx.MockTransport(handler), sleep=_noop_sleep, refresh=refresh
        )

        items = await client.paginate("/generic", limit=10)

        assert [item["id"] for item in items] == ["after-retry-item"]
        assert refresh_calls == 1
        assert seen_tokens == ["Bearer test-access-token", "Bearer fresh-access-token"]
        assert sink_calls[0].access_token == "fresh-access-token"

    @pytest.mark.asyncio
    async def test_revoked_refresh_token_raises_controlled_error_without_looping(
        self,
    ) -> None:
        """Scenario: `refresh_token` revocado — the refresh callable itself
        rejects the refresh; the client raises a controlled reconnection
        error and NEVER loops (only ONE 401 request is ever made)."""

        from app.integrations.adapters.microsoft365.client import GraphClient
        from app.shared.exceptions import AppException

        unauthorized = _load_fixture("unauthorized_401.json")
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(401, json=unauthorized)

        async def revoked_refresh(refresh_token: str) -> None:
            raise RuntimeError("invalid_grant: refresh token revoked")

        client = GraphClient(
            _ctx(),
            transport=httpx.MockTransport(handler),
            sleep=_noop_sleep,
            refresh=revoked_refresh,
        )

        with pytest.raises(AppException) as excinfo:
            await client.paginate("/generic", limit=10)

        assert excinfo.value.code == "oauth_token_invalid"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_429_honors_retry_after_and_succeeds(self) -> None:
        """Scenario: Retry-After se respeta y agotamiento controlado — a
        `429` with `Retry-After` makes the client sleep at least that long
        (via the injected `sleep`) before retrying, then completes on
        success (M365-R7)."""

        from app.integrations.adapters.microsoft365.client import GraphClient

        throttled = _load_fixture("throttled_429.json")
        ok = _load_fixture("ok_after_retry.json")
        sleep_calls: list[float] = []
        call_count = 0

        async def spy_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(
                    429, json=throttled, headers={"Retry-After": "2"}
                )
            return httpx.Response(200, json=ok)

        client = GraphClient(
            _ctx(), transport=httpx.MockTransport(handler), sleep=spy_sleep
        )

        items = await client.paginate("/generic", limit=10)

        assert [item["id"] for item in items] == ["after-retry-item"]
        assert sleep_calls == [2.0]
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_429_beyond_max_retries_raises_controlled_error(self) -> None:
        """Scenario (agotamiento): `429` repeated past `M365_MAX_RETRIES`
        raises a controlled error instead of retrying forever."""

        from app.integrations.adapters.microsoft365.client import GraphClient
        from app.shared.exceptions import AppException

        throttled = _load_fixture("throttled_429.json")
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(429, json=throttled, headers={"Retry-After": "1"})

        settings = _settings(M365_MAX_RETRIES=2)
        client = GraphClient(
            _ctx(),
            transport=httpx.MockTransport(handler),
            sleep=_noop_sleep,
            settings=settings,
        )

        with pytest.raises(AppException) as excinfo:
            await client.paginate("/generic", limit=10)

        assert excinfo.value.code == "provider_throttled"
        assert call_count == 1 + settings.M365_MAX_RETRIES

    @pytest.mark.asyncio
    async def test_no_token_leaks_in_caplog_or_exception_message(
        self, caplog
    ) -> None:
        """Neither the access token nor the refresh token used in a request
        that fails ever appears in a log record or in the raised
        exception's message (M365-R3/M365-R7 threat matrix, "sin fuga de
        tokens")."""

        from app.integrations.adapters.microsoft365.client import GraphClient
        from app.shared.exceptions import AppException

        unauthorized = _load_fixture("unauthorized_401.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json=unauthorized)

        async def revoked_refresh(refresh_token: str) -> None:
            raise RuntimeError("invalid_grant")

        ctx = _ctx(
            access_token="super-secret-access-token",
            refresh_token="super-secret-refresh-token",
        )
        client = GraphClient(
            ctx,
            transport=httpx.MockTransport(handler),
            sleep=_noop_sleep,
            refresh=revoked_refresh,
        )

        with caplog.at_level("DEBUG"):
            with pytest.raises(AppException) as excinfo:
                await client.paginate("/generic", limit=10)

        assert "super-secret-access-token" not in str(excinfo.value)
        assert "super-secret-refresh-token" not in str(excinfo.value)
        assert "super-secret-access-token" not in caplog.text
        assert "super-secret-refresh-token" not in caplog.text
