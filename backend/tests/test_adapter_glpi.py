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


# ---------------------------------------------------------------------------
# Lote 6 — Adaptador completo: mapper + adapter + errors + registro
# ---------------------------------------------------------------------------


class TestGlpiMapper:
    """Pure JSON -> DTO translation, no I/O (mapper.py)."""

    def test_map_person_uses_default_flagged_email_and_configured_document_field(
        self,
    ) -> None:
        from app.integrations.adapters.glpi.mapper import map_person

        user_json = _load_fixture("user.json")
        emails_json = _load_fixture("user_email.json")

        person = map_person(user_json, emails_json, document_field="registration_number")

        assert person.external_id == "55"
        assert person.display_name == "Ana Torres"
        assert person.email == "ana.torres@example.com"
        assert person.document == "123456789"

    def test_map_person_falls_back_to_first_email_when_none_flagged_default(
        self,
    ) -> None:
        """Triangulation: no `is_default` entry -> the FIRST email wins."""

        from app.integrations.adapters.glpi.mapper import map_person

        user_json = {"id": 9, "firstname": "Carlos", "realname": "Ruiz"}
        emails_json = [
            {"email": "carlos.alt@example.com", "is_default": 0},
            {"email": "carlos.ruiz@example.com", "is_default": 0},
        ]

        person = map_person(user_json, emails_json, document_field="registration_number")

        assert person.email == "carlos.alt@example.com"
        assert person.document is None

    def test_map_ticket_includes_assignees_and_requester(self) -> None:
        from app.integrations.adapters.glpi.mapper import map_person, map_ticket

        ticket_json = {
            "id": 201,
            "name": "Impresora no imprime",
            "status": 2,
            "priority": 3,
            "date": "2026-07-01 09:00:00",
        }
        assignee = map_person(
            _load_fixture("user.json"),
            _load_fixture("user_email.json"),
            document_field="registration_number",
        )

        ticket = map_ticket(ticket_json, assignees=(assignee,), requester="Diana Páez")

        assert ticket.external_id == "201"
        assert ticket.key == "GLPI-201"
        assert ticket.summary == "Impresora no imprime"
        assert ticket.assignees == (assignee,)
        assert ticket.requester == "Diana Páez"

    def test_map_ticket_without_assignees_has_empty_tuple(self) -> None:
        from app.integrations.adapters.glpi.mapper import map_ticket

        ticket = map_ticket(
            {"id": 202, "name": "Solo solicitante", "status": 1, "priority": None},
            assignees=(),
            requester="Diana Páez",
        )

        assert ticket.assignees == ()
        assert ticket.requester == "Diana Páez"
        assert ticket.priority is None


def _glpi_routing_handler(
    *,
    ticket_pages: dict[str, tuple[list[dict], str]],
    ticket_users_by_ticket: dict[str, list[dict]],
    users_by_id: dict[str, dict],
    emails_by_user: dict[str, list[dict]],
    init_fails: bool = False,
):
    """Build a single `httpx.MockTransport` handler routing GLPI's session
    lifecycle + `Ticket`/`Ticket_User`/`User`/`UserEmail` endpoints from
    canned fixtures — shared by every Lote 6 adapter-level test."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/initSession"):
            if init_fails:
                return httpx.Response(
                    401, json=_load_fixture("session_expired_401.json")
                )
            return httpx.Response(200, json={"session_token": _FRESH_TOKEN})
        if path.endswith("/killSession"):
            return httpx.Response(200, json={})
        if path.endswith("/Ticket_User"):
            ticket_id = path.rsplit("/", 2)[1]
            return httpx.Response(200, json=ticket_users_by_ticket.get(ticket_id, []))
        if path.endswith("/UserEmail"):
            user_id = path.rsplit("/", 2)[1]
            return httpx.Response(200, json=emails_by_user.get(user_id, []))
        if "/User/" in path:
            user_id = path.rsplit("/", 1)[1]
            return httpx.Response(200, json=users_by_id.get(user_id, {}))
        if path.endswith("/Ticket"):
            range_header = request.headers.get("Range", "0-99")
            items, content_range = ticket_pages.get(range_header, ([], "0-0/0"))
            return httpx.Response(206, json=items, headers={"Content-Range": content_range})
        return httpx.Response(404, json={"error": "not_found"})

    return handler


def _ctx_for(connector_id: str, *, document_field: str | None = None):
    from app.integrations.adapters.glpi.adapter import encode_access_context
    from app.integrations.ports import AccessContext

    payload = encode_access_context(
        connector_id=connector_id,
        base_url=_ALLOWED_BASE_URL,
        app_token="app-token-xyz",
        user_token="user-token-abc",
        document_field=document_field,
    )
    return AccessContext(access_token=payload, refresh_token=None, scopes=())


def _glpi_adapter_for(handler) -> object:
    """Build a `GlpiAdapter` whose tickets port routes every HTTP call
    through `handler` via an injected `httpx.MockTransport` — zero real
    network, no monkeypatching (the adapter/`_GlpiTicketReader` accept an
    injectable `transport`, same DI shape as `GraphClient`/`GoogleClient`).
    """

    from app.integrations.adapters.glpi.adapter import GlpiAdapter

    return GlpiAdapter(settings=_settings(), transport=httpx.MockTransport(handler))


class TestGlpiAdapterListTickets:
    @pytest.mark.asyncio
    async def test_ticket_with_assigned_technician_populates_assignees(
        self, patched_redis
    ) -> None:
        """GA-R4, Scenario "Ticket con un técnico asignado"."""

        from app.integrations.ports import Capability

        ticket_json = {
            "id": 201,
            "name": "Impresora no imprime",
            "status": 2,
            "priority": 3,
            "date": "2026-07-01 09:00:00",
        }
        handler = _glpi_routing_handler(
            ticket_pages={"0-49": ([ticket_json], "0-0/1")},
            ticket_users_by_ticket={"201": _load_fixture("ticket_user_assigned.json")},
            users_by_id={"55": _load_fixture("user.json")},
            emails_by_user={"55": _load_fixture("user_email.json")},
        )

        adapter = _glpi_adapter_for(handler)
        port = adapter.port_for(Capability.tickets)
        tickets = await port.list_tickets(_ctx_for("conn-a"), limit=50)

        assert len(tickets) == 1
        ticket = tickets[0]
        assert ticket.external_id == "201"
        assert len(ticket.assignees) == 1
        assert ticket.assignees[0].display_name == "Ana Torres"
        assert ticket.assignees[0].email == "ana.torres@example.com"
        assert ticket.assignees[0].document == "123456789"

    @pytest.mark.asyncio
    async def test_ticket_with_requester_only_has_empty_assignees(
        self, patched_redis
    ) -> None:
        """GA-R4, Scenario "Ticket con solicitante pero sin asignado"."""

        from app.integrations.ports import Capability

        ticket_json = {
            "id": 202,
            "name": "Solo solicitante",
            "status": 1,
            "priority": 1,
            "date": "2026-07-02 09:00:00",
        }
        requester_user = {
            "id": 77,
            "name": "dpaez",
            "realname": "Páez",
            "firstname": "Diana",
        }
        handler = _glpi_routing_handler(
            ticket_pages={"0-49": ([ticket_json], "0-0/1")},
            ticket_users_by_ticket={
                "202": _load_fixture("ticket_user_requester_only.json")
            },
            users_by_id={"77": requester_user},
            emails_by_user={},
        )

        adapter = _glpi_adapter_for(handler)
        port = adapter.port_for(Capability.tickets)
        tickets = await port.list_tickets(_ctx_for("conn-b"), limit=50)

        assert len(tickets) == 1
        ticket = tickets[0]
        assert ticket.assignees == ()
        assert ticket.requester == "Diana Páez"


class TestGlpiWriteBoundary:
    def test_no_write_http_verb_used_anywhere_except_init_session(self) -> None:
        """GA-R5, Scenario "No existe ningún método de escritura" — static
        source inspection: `.post(` appears exactly once (init_session's
        `POST /initSession`, part of the session cycle); `.put(`/`.delete(`
        never appear anywhere in the package."""

        import inspect

        from app.integrations.adapters.glpi import adapter, client

        source = inspect.getsource(client) + inspect.getsource(adapter)
        assert source.count(".post(") == 1
        assert ".put(" not in source
        assert ".delete(" not in source


class TestGlpiErrors:
    @pytest.mark.asyncio
    async def test_network_error_raises_glpi_unavailable(self, patched_redis) -> None:
        """GA-R6, Scenario "GLPI no responde"."""

        from app.integrations.adapters.glpi import errors
        from app.integrations.ports import Capability

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        adapter = _glpi_adapter_for(handler)
        port = adapter.port_for(Capability.tickets)
        with pytest.raises(errors.GlpiUnavailable):
            await port.list_tickets(_ctx_for("conn-c"), limit=50)

    @pytest.mark.asyncio
    async def test_invalid_credentials_raise_glpi_auth_error_without_caching(
        self, patched_redis, fake_redis
    ) -> None:
        """GA-R6, Scenario "Credenciales inválidas"."""

        from app.integrations.adapters.glpi import errors
        from app.integrations.ports import Capability

        handler = _glpi_routing_handler(
            ticket_pages={},
            ticket_users_by_ticket={},
            users_by_id={},
            emails_by_user={},
            init_fails=True,
        )

        adapter = _glpi_adapter_for(handler)
        port = adapter.port_for(Capability.tickets)
        with pytest.raises(errors.GlpiAuthError):
            await port.list_tickets(_ctx_for("conn-d"), limit=50)

        cached = await fake_redis.get(_session_key("conn-d"))
        assert cached is None


class TestGlpiMultiTenant:
    @pytest.mark.asyncio
    async def test_two_connectors_use_isolated_session_cache_keys(
        self, patched_redis, fake_redis
    ) -> None:
        """GA-R7, Scenario "Dos organizaciones con conectores GLPI
        distintos" — each `connector_id` gets its OWN Redis key, no
        cross-talk even when both point at the same GLPI instance."""

        from app.integrations.ports import Capability

        handler = _glpi_routing_handler(
            ticket_pages={"0-49": ([], "0-0/0")},
            ticket_users_by_ticket={},
            users_by_id={},
            emails_by_user={},
        )

        adapter = _glpi_adapter_for(handler)
        port = adapter.port_for(Capability.tickets)
        await port.list_tickets(_ctx_for("conn-org-a"), limit=50)
        await port.list_tickets(_ctx_for("conn-org-b"), limit=50)

        assert await fake_redis.get(_session_key("conn-org-a")) == _FRESH_TOKEN
        assert await fake_redis.get(_session_key("conn-org-b")) == _FRESH_TOKEN


class TestGlpiRegistration:
    def test_glpi_adapter_registered_at_import_time_with_correct_shape(self) -> None:
        """GA-R1, Scenario "Registro sin tocar el núcleo"."""

        import app.integrations.adapters.glpi  # noqa: F401 - triggers registration
        from app.integrations.ports import Capability, CredentialKind
        from app.integrations.registry import get_adapter

        resolved = get_adapter("glpi")
        assert resolved is not None
        assert resolved.provider == "glpi"
        assert resolved.credential_kind == CredentialKind.api_token
        assert resolved.capabilities == frozenset({Capability.tickets})
        assert resolved.oauth is None
        assert resolved.api_token is not None


class TestGlpiApiTokenHandshake:
    """GA-R2 (connect-time validation): `ApiTokenHandshake.connect(raw)`
    validates via `initSession`+`killSession`, never persists anything
    itself (that stays `connectors/service.py`'s job)."""

    @pytest.mark.asyncio
    async def test_connect_validates_via_init_and_kill_session_and_returns_account_ref(
        self,
    ) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/initSession"):
                calls.append("init")
                return httpx.Response(200, json={"session_token": _FRESH_TOKEN})
            if request.url.path.endswith("/killSession"):
                calls.append("kill")
                return httpx.Response(200, json={})
            return httpx.Response(404)

        adapter = _glpi_adapter_for(handler)

        account_ref = await adapter.api_token.connect(
            {
                "base_url": _ALLOWED_BASE_URL,
                "app_token": "app-token-xyz",
                "user_token": "user-token-abc",
            }
        )

        assert calls == ["init", "kill"]
        assert account_ref.external_account_id.startswith("glpi-")

    @pytest.mark.asyncio
    async def test_connect_with_invalid_credentials_raises_glpi_auth_error(self) -> None:
        from app.integrations.adapters.glpi import errors

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json=_load_fixture("session_expired_401.json"))

        adapter = _glpi_adapter_for(handler)

        with pytest.raises(errors.GlpiAuthError):
            await adapter.api_token.connect(
                {
                    "base_url": _ALLOWED_BASE_URL,
                    "app_token": "app-token-xyz",
                    "user_token": "user-token-invalid",
                }
            )
