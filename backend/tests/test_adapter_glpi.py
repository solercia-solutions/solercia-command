"""RED tests for the `glpi` adapter (change 17-adapter-glpi,
specs/glpi-adapter/spec.md). Read-only adapter over GLPI's `apirest.php`,
`credential_kind=api_token` (App-Token + user_token -> `initSession`).

Every test runs against `httpx.MockTransport` fixtures under
`tests/fixtures/glpi/` — ZERO real network in CI (design.md "TDD estricto
con httpx.MockTransport"). Classes are grouped by work unit/lote so
`pytest -k` can target a single batch's RED/GREEN cycle:
    TestGlpiClientBase    — Lote 4 (initSession/killSession + paginación Range + anti-SSRF)
    TestGlpiSessionCache  — Lote 5 (session_token en Redis + reinicio ante 401)
    TestGlpiMapper        — Lote 6 (JSON GLPI -> Ticket/ExternalPerson)
    TestGlpiWriteBoundary — Lote 6 (frontera de solo lectura)
    TestGlpiErrors        — Lote 6 (GLPI inaccesible / credenciales inválidas)
    TestGlpiMultiTenant   — Lote 6 (aislamiento por connector_id)
"""

import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "glpi"

_ALLOWED_BASE_URL = "http://localhost:8080/glpi/apirest.php"


def _load_fixture(name: str) -> dict | list:
    """Load a GLPI response fixture by filename from `tests/fixtures/glpi/`."""

    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _settings(**overrides: object) -> Settings:
    """Build a real `Settings` instance with `GLPI_*` overrides for a test."""

    defaults: dict[str, object] = {"GLPI_BASE_URL_ALLOWLIST": [_ALLOWED_BASE_URL]}
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Lote 4 — Cliente GLPI base: initSession/killSession + paginación Range +
# allowlist anti-SSRF
# ---------------------------------------------------------------------------


class TestGlpiClientBase:
    def test_rejects_base_url_without_http_scheme_before_any_request(self) -> None:
        """Threat Matrix (SSRF): a `base_url` without `http(s)://` is
        rejected in the constructor — zero HTTP calls are ever made."""

        from app.integrations.adapters.glpi.client import GlpiClient, GlpiConfigError

        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        with pytest.raises(GlpiConfigError):
            GlpiClient(
                "ftp://glpi.internal/apirest.php",
                transport=httpx.MockTransport(handler),
                settings=_settings(),
            )
        assert calls == 0

    def test_rejects_base_url_outside_allowlist_before_any_request(self) -> None:
        """Threat Matrix (SSRF): a syntactically valid `http(s)://` URL that
        is NOT in `GLPI_BASE_URL_ALLOWLIST` is rejected — zero HTTP calls."""

        from app.integrations.adapters.glpi.client import GlpiClient, GlpiConfigError

        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        with pytest.raises(GlpiConfigError):
            GlpiClient(
                "http://169.254.169.254/apirest.php",
                transport=httpx.MockTransport(handler),
                settings=_settings(),
            )
        assert calls == 0

    def test_accepts_a_base_url_present_in_the_allowlist(self) -> None:
        """The happy path: a `base_url` that IS in the allowlist constructs
        without raising."""

        from app.integrations.adapters.glpi.client import GlpiClient

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={})

        client = GlpiClient(
            _ALLOWED_BASE_URL,
            transport=httpx.MockTransport(handler),
            settings=_settings(),
        )
        assert client is not None

    @pytest.mark.asyncio
    async def test_init_session_sends_app_token_and_user_token_and_returns_session_token(
        self,
    ) -> None:
        """`initSession` sends `App-Token` + `Authorization: user_token ...`
        and returns the `session_token` from the response."""

        from app.integrations.adapters.glpi.client import GlpiClient

        payload = _load_fixture("init_session.json")
        seen_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal seen_request
            seen_request = request
            return httpx.Response(200, json=payload)

        client = GlpiClient(
            _ALLOWED_BASE_URL,
            transport=httpx.MockTransport(handler),
            settings=_settings(),
        )

        session_token = await client.init_session("app-token-xyz", "user-token-abc")

        assert session_token == "glpi-session-token-abc123"
        assert seen_request is not None
        assert seen_request.headers["App-Token"] == "app-token-xyz"
        assert seen_request.headers["Authorization"] == "user_token user-token-abc"
        assert seen_request.method == "POST"
        assert seen_request.url.path.endswith("/initSession")

    @pytest.mark.asyncio
    async def test_kill_session_sends_session_token_and_app_token(self) -> None:
        """`killSession` sends `Session-Token` + `App-Token`."""

        from app.integrations.adapters.glpi.client import GlpiClient

        payload = _load_fixture("kill_session.json")
        seen_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal seen_request
            seen_request = request
            return httpx.Response(200, json=payload)

        client = GlpiClient(
            _ALLOWED_BASE_URL,
            transport=httpx.MockTransport(handler),
            settings=_settings(),
        )

        await client.kill_session("glpi-session-token-abc123", "app-token-xyz")

        assert seen_request is not None
        assert seen_request.headers["Session-Token"] == "glpi-session-token-abc123"
        assert seen_request.headers["App-Token"] == "app-token-xyz"
        assert seen_request.method == "GET"
        assert seen_request.url.path.endswith("/killSession")

    @pytest.mark.asyncio
    async def test_list_tickets_paginates_via_range_header_until_exhausted(
        self,
    ) -> None:
        """Scenario: paginación por header `Range` ensambla ambas páginas
        hasta agotar `Content-Range` — 3 tickets total across 2 pages of 2."""

        from app.integrations.adapters.glpi.client import GlpiClient

        page_1 = _load_fixture("ticket_page_1.json")
        page_2 = _load_fixture("ticket_page_2.json")
        seen_ranges: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            range_header = request.headers.get("Range", "")
            seen_ranges.append(range_header)
            if range_header == "0-1":
                return httpx.Response(
                    206, json=page_1, headers={"Content-Range": "0-1/3"}
                )
            return httpx.Response(206, json=page_2, headers={"Content-Range": "2-2/3"})

        client = GlpiClient(
            _ALLOWED_BASE_URL,
            transport=httpx.MockTransport(handler),
            settings=_settings(GLPI_PAGE_SIZE=2),
        )

        tickets = await client.list_tickets(
            "glpi-session-token-abc123", "app-token-xyz", range_start=0, range_end=99
        )

        assert [t["id"] for t in tickets] == [101, 102, 103]
        assert seen_ranges == ["0-1", "2-3"]

    @pytest.mark.asyncio
    async def test_list_tickets_single_page_stops_after_content_range_total(
        self,
    ) -> None:
        """A `Content-Range` total that fits within the first page never
        issues a second request."""

        from app.integrations.adapters.glpi.client import GlpiClient

        page_1 = _load_fixture("ticket_page_1.json")
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(206, json=page_1, headers={"Content-Range": "0-1/2"})

        client = GlpiClient(
            _ALLOWED_BASE_URL,
            transport=httpx.MockTransport(handler),
            settings=_settings(GLPI_PAGE_SIZE=2),
        )

        tickets = await client.list_tickets(
            "glpi-session-token-abc123", "app-token-xyz", range_start=0, range_end=99
        )

        assert len(tickets) == 2
        assert call_count == 1
