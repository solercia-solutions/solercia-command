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
