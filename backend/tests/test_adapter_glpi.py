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


# ---------------------------------------------------------------------------
# Lote 5 — Cache de session_token en Redis + reinicio ante 401
# ---------------------------------------------------------------------------

_CONNECTOR_ID = "conn-glpi-1"
_STALE_TOKEN = "stale-session-token"
_FRESH_TOKEN = "fresh-session-token-after-reinit"


def _session_key(connector_id: str) -> str:
    return f"glpi:session:{connector_id}"


class TestGlpiSessionCache:
    @pytest.mark.asyncio
    async def test_first_read_without_cache_calls_init_session_and_caches_it(
        self, patched_redis, fake_redis
    ) -> None:
        """Scenario: Primera llamada inicia sesión y cachea — no cached
        entry yet, so `init_session` is called once and the result is
        `SETEX`'d under `glpi:session:{connector_id}` with the configured
        TTL."""

        from app.integrations.adapters.glpi import session as glpi_session
        from app.integrations.adapters.glpi.client import GlpiClient

        init_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal init_calls
            init_calls += 1
            return httpx.Response(200, json={"session_token": _FRESH_TOKEN})

        client = GlpiClient(
            _ALLOWED_BASE_URL,
            transport=httpx.MockTransport(handler),
            settings=_settings(GLPI_SESSION_TTL_SECONDS=3300),
        )

        token = await glpi_session.get_or_init_session(
            _CONNECTOR_ID, client, "app-token-xyz", "user-token-abc", settings=_settings()
        )

        assert token == _FRESH_TOKEN
        assert init_calls == 1
        cached = await fake_redis.get(_session_key(_CONNECTOR_ID))
        assert cached == _FRESH_TOKEN
        ttl = await fake_redis.ttl(_session_key(_CONNECTOR_ID))
        assert 0 < ttl <= 3300

    @pytest.mark.asyncio
    async def test_second_read_reuses_the_cached_session_without_reinit(
        self, patched_redis, fake_redis
    ) -> None:
        """Scenario: Llamada subsiguiente reutiliza el cache — a
        pre-populated cache entry means `init_session` is NEVER called."""

        from app.integrations.adapters.glpi import session as glpi_session
        from app.integrations.adapters.glpi.client import GlpiClient

        await fake_redis.set(_session_key(_CONNECTOR_ID), _STALE_TOKEN, ex=3300)
        init_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal init_calls
            init_calls += 1
            return httpx.Response(200, json={"session_token": _FRESH_TOKEN})

        client = GlpiClient(
            _ALLOWED_BASE_URL, transport=httpx.MockTransport(handler), settings=_settings()
        )

        token = await glpi_session.get_or_init_session(
            _CONNECTOR_ID, client, "app-token-xyz", "user-token-abc", settings=_settings()
        )

        assert token == _STALE_TOKEN
        assert init_calls == 0

    @pytest.mark.asyncio
    async def test_401_invalidates_cache_reinits_and_retries_transparently(
        self, patched_redis, fake_redis
    ) -> None:
        """Scenario: Expiración detectada durante una lectura —
        `with_session_retry` invalidates the stale cache entry, calls
        `init_session` exactly once and retries the ORIGINAL operation with
        the fresh token, transparently returning its result."""

        from app.integrations.adapters.glpi import session as glpi_session
        from app.integrations.adapters.glpi.client import GlpiClient

        await fake_redis.set(_session_key(_CONNECTOR_ID), _STALE_TOKEN, ex=3300)
        ticket_page = _load_fixture("ticket_page_1.json")
        init_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal init_calls
            if request.url.path.endswith("/initSession"):
                init_calls += 1
                return httpx.Response(200, json={"session_token": _FRESH_TOKEN})
            token = request.headers.get("Session-Token")
            if token == _STALE_TOKEN:
                return httpx.Response(
                    401, json=_load_fixture("session_expired_401.json")
                )
            return httpx.Response(
                206, json=ticket_page, headers={"Content-Range": "0-1/2"}
            )

        client = GlpiClient(
            _ALLOWED_BASE_URL, transport=httpx.MockTransport(handler), settings=_settings()
        )

        async def _operation(session_token: str) -> list[dict]:
            return await client.list_tickets(
                session_token, "app-token-xyz", range_start=0, range_end=1
            )

        result = await glpi_session.with_session_retry(
            _CONNECTOR_ID,
            client,
            "app-token-xyz",
            "user-token-abc",
            _operation,
            settings=_settings(),
        )

        assert [t["id"] for t in result] == [101, 102]
        assert init_calls == 1
        cached = await fake_redis.get(_session_key(_CONNECTOR_ID))
        assert cached == _FRESH_TOKEN

    @pytest.mark.asyncio
    async def test_reinit_failure_after_401_propagates_without_caching_invalid_token(
        self, patched_redis, fake_redis
    ) -> None:
        """Scenario: Reinicio de sesión falla — credenciales revocadas: the
        retried `init_session` ALSO fails, so a controlled error propagates
        and NO `session_token` (valid or invalid) is left cached."""

        from app.integrations.adapters.glpi import session as glpi_session
        from app.integrations.adapters.glpi.client import GlpiClient

        await fake_redis.set(_session_key(_CONNECTOR_ID), _STALE_TOKEN, ex=3300)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json=_load_fixture("session_expired_401.json"))

        client = GlpiClient(
            _ALLOWED_BASE_URL, transport=httpx.MockTransport(handler), settings=_settings()
        )

        async def _operation(session_token: str) -> list[dict]:
            return await client.list_tickets(
                session_token, "app-token-xyz", range_start=0, range_end=1
            )

        with pytest.raises(httpx.HTTPStatusError):
            await glpi_session.with_session_retry(
                _CONNECTOR_ID,
                client,
                "app-token-xyz",
                "user-token-abc",
                _operation,
                settings=_settings(),
            )

        cached = await fake_redis.get(_session_key(_CONNECTOR_ID))
        assert cached is None

    @pytest.mark.asyncio
    async def test_no_secret_leaks_in_logs_or_exception_text(
        self, patched_redis, fake_redis, caplog
    ) -> None:
        """Threat Matrix (sin fuga de secretos): neither the `session_token`,
        `app_token` nor `user_token` values ever appear in `caplog` or in
        `str(exception)` across a full invalidate+reinit-failure cycle."""

        import logging

        from app.integrations.adapters.glpi import session as glpi_session
        from app.integrations.adapters.glpi.client import GlpiClient

        app_token = "APP-TOKEN-SECRET-VALUE"
        user_token = "USER-TOKEN-SECRET-VALUE"
        await fake_redis.set(_session_key(_CONNECTOR_ID), _STALE_TOKEN, ex=3300)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json=_load_fixture("session_expired_401.json"))

        client = GlpiClient(
            _ALLOWED_BASE_URL, transport=httpx.MockTransport(handler), settings=_settings()
        )

        async def _operation(session_token: str) -> list[dict]:
            return await client.list_tickets(session_token, app_token, range_start=0, range_end=1)

        caught: Exception | None = None
        with caplog.at_level(logging.DEBUG):
            try:
                await glpi_session.with_session_retry(
                    _CONNECTOR_ID,
                    client,
                    app_token,
                    user_token,
                    _operation,
                    settings=_settings(),
                )
            except Exception as exc:  # noqa: BLE001 - captured for assertion below
                caught = exc

        assert caught is not None
        assert app_token not in str(caught)
        assert user_token not in str(caught)
        assert _STALE_TOKEN not in str(caught)
        for record in caplog.records:
            assert app_token not in record.getMessage()
            assert user_token not in record.getMessage()
            assert _STALE_TOKEN not in record.getMessage()
