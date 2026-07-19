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
from datetime import UTC, datetime
from pathlib import Path

import httpx
import jwt as pyjwt
import pytest

from app.config import Settings
from app.integrations.ports import AccessContext
from tests.conftest import TwoOrgs, skip_no_db

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


# ---------------------------------------------------------------------------
# Lote 3 — OAuth Entra ID + registro del adaptador
# ---------------------------------------------------------------------------


class TestOAuthAndRegistry:
    def test_authorize_url_uses_organizations_tenant_by_default(self) -> None:
        """Scenario: Tenant por defecto y override por configuración — no
        tenant override → the authorize URL uses ``organizations``."""

        from app.integrations.adapters.microsoft365 import oauth

        settings = _settings(M365_CLIENT_ID="client-abc")

        url = oauth.authorize_url(
            "state-1", "https://app.test/callback", ["User.Read"], settings=settings
        )

        assert url.startswith(
            "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize"
        )
        assert "state=state-1" in url
        assert "client_id=client-abc" in url
        assert "redirect_uri=https%3A%2F%2Fapp.test%2Fcallback" in url

    def test_authorize_url_uses_the_configured_tenant_override(self) -> None:
        """Scenario (continuación): un tenant fijo por variable de entorno
        hace que la URL use ESE tenant en su lugar."""

        from app.integrations.adapters.microsoft365 import oauth

        settings = _settings(M365_TENANT="contoso.onmicrosoft.com")

        url = oauth.authorize_url(
            "state-1", "https://app.test/callback", ["User.Read"], settings=settings
        )

        assert url.startswith(
            "https://login.microsoftonline.com/contoso.onmicrosoft.com"
            "/oauth2/v2.0/authorize"
        )

    @pytest.mark.asyncio
    async def test_exchange_code_returns_tokens_with_oid_as_external_account_id(
        self,
    ) -> None:
        """`OAuthTokens.external_account_id` is the token response's
        ``id_token`` ``oid`` claim (design.md ADR #5 — stable, unlike the
        UPN)."""

        from app.integrations.adapters.microsoft365 import oauth

        id_token = pyjwt.encode(
            {"oid": "11111111-2222-3333-4444-555555555555", "upn": "ana@contoso.com"},
            "unused-signing-secret",
            algorithm="HS256",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/organizations/oauth2/v2.0/token"
            return httpx.Response(
                200,
                json={
                    "access_token": "graph-access-token",
                    "refresh_token": "graph-refresh-token",
                    "id_token": id_token,
                    "expires_in": 3600,
                    "scope": "Mail.Read Calendars.Read",
                },
            )

        tokens = await oauth.exchange_code(
            "auth-code-1",
            "https://app.test/callback",
            transport=httpx.MockTransport(handler),
        )

        assert tokens.external_account_id == "11111111-2222-3333-4444-555555555555"
        assert tokens.access_token == "graph-access-token"
        assert tokens.refresh_token == "graph-refresh-token"
        assert tokens.scopes == ("Mail.Read", "Calendars.Read")
        assert tokens.expires_at is not None

    @pytest.mark.asyncio
    async def test_refresh_returns_tokens_with_oid_as_external_account_id(self) -> None:
        """Same ``oid`` extraction applies to the ``refresh_token`` grant."""

        from app.integrations.adapters.microsoft365 import oauth

        id_token = pyjwt.encode(
            {"oid": "99999999-8888-7777-6666-555555555555"},
            "unused-signing-secret",
            algorithm="HS256",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "access_token": "rotated-access-token",
                    "refresh_token": "rotated-refresh-token",
                    "id_token": id_token,
                    "expires_in": 3600,
                    "scope": "Mail.Read",
                },
            )

        tokens = await oauth.refresh(
            "some-refresh-token", transport=httpx.MockTransport(handler)
        )

        assert tokens.external_account_id == "99999999-8888-7777-6666-555555555555"
        assert tokens.access_token == "rotated-access-token"

    @pytest.mark.asyncio
    async def test_no_token_leaks_in_caplog_or_exception_message_for_oauth(
        self, caplog
    ) -> None:
        """Threat Matrix (oauth.py half): a token endpoint rejection never
        surfaces the refresh token used in the request, in a log record or
        in the raised exception's message."""

        from app.integrations.adapters.microsoft365 import oauth
        from app.shared.exceptions import AppException

        def handler(request: httpx.Request) -> httpx.Response:
            assert "super-secret-refresh-token" in request.content.decode()
            return httpx.Response(400, json={"error": "invalid_grant"})

        with caplog.at_level("DEBUG"):
            with pytest.raises(AppException) as excinfo:
                await oauth.refresh(
                    "super-secret-refresh-token",
                    transport=httpx.MockTransport(handler),
                )

        assert "super-secret-refresh-token" not in str(excinfo.value)
        assert "super-secret-refresh-token" not in caplog.text

    def test_get_adapter_returns_microsoft365_instance_without_editing_the_core(
        self,
    ) -> None:
        """Scenario: Registro sin tocar el núcleo ni declarar tickets — the
        core's registry resolves ``provider="microsoft365"`` to this
        adapter's instance purely because the adapter's OWN module ran
        ``register_adapter(...)`` at import time (IP-R2)."""

        import app.integrations.adapters.microsoft365  # noqa: F401
        from app.integrations.adapters.microsoft365.adapter import Microsoft365Adapter
        from app.integrations.registry import get_adapter

        resolved = get_adapter("microsoft365")

        assert resolved is not None
        assert isinstance(resolved, Microsoft365Adapter)

    def test_tickets_capability_is_not_declared(self) -> None:
        """Scenario (continuación): ``tickets`` no aparece entre sus
        capacidades declaradas — 17-18 cover ticket providers, not this
        adapter."""

        from app.integrations.adapters.microsoft365.adapter import Microsoft365Adapter
        from app.integrations.ports import Capability

        adapter = Microsoft365Adapter()

        assert Capability.tickets not in adapter.capabilities
        assert adapter.provider == "microsoft365"

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_authorize_route_redirects_to_entra_id_for_a_microsoft365_connector(
        self, client: httpx.AsyncClient, two_orgs: TwoOrgs, patched_redis
    ) -> None:
        """Runtime harness (Unit 3): a REAL ``microsoft365`` connector,
        hitting the 14's EXISTING ``GET /connectors/{id}/authorize`` route,
        302s straight to ``login.microsoftonline.com`` — proves the
        registration end-to-end through the 14's own router, without
        touching it."""

        create_response = await client.post(
            "/connectors",
            json={"provider": "microsoft365"},
            headers={"Authorization": f"Bearer {two_orgs.a.token}"},
        )
        assert create_response.status_code == 201, create_response.text
        connector_id = create_response.json()["data"]["id"]

        authorize_response = await client.get(
            f"/connectors/{connector_id}/authorize",
            headers={"Authorization": f"Bearer {two_orgs.a.token}"},
        )

        assert authorize_response.status_code == 302, authorize_response.text
        location = authorize_response.headers["location"]
        assert location.startswith("https://login.microsoftonline.com/")


# ---------------------------------------------------------------------------
# Lote 4 — Correo: `MailReaderPort`
# ---------------------------------------------------------------------------


class TestMailPort:
    @pytest.mark.asyncio
    async def test_list_messages_aggregates_dtos_from_two_pages_respecting_limit(
        self,
    ) -> None:
        """Scenario: Resultados dentro de la ventana, multi-página (M365-R4,
        correo) — two fixture pages chained by `@odata.nextLink` are fully
        aggregated into `MailMessage` DTOs, Graph's own pagination never
        leaks into them."""

        from app.integrations.adapters.microsoft365.ports import GraphMailReader
        from app.integrations.dtos import MailMessage

        page_1 = _load_fixture("mail_page_1.json")
        page_2 = _load_fixture("mail_page_2.json")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.params.get("$skip") == "2":
                return httpx.Response(200, json=page_2)
            assert request.url.path == "/v1.0/me/messages"
            assert "receivedDateTime ge" in request.url.params.get("$filter", "")
            return httpx.Response(200, json=page_1)

        port = GraphMailReader(transport=httpx.MockTransport(handler))

        messages = await port.list_messages(_ctx(), limit=10)

        assert [m.external_id for m in messages] == ["mail-1", "mail-2", "mail-3"]
        assert all(isinstance(m, MailMessage) for m in messages)

    @pytest.mark.asyncio
    async def test_list_messages_returns_empty_list_without_error(self) -> None:
        """Scenario: Sin resultados en la ventana — an empty `value` never
        raises, it returns an empty list (M365-R4, correo)."""

        from app.integrations.adapters.microsoft365.ports import GraphMailReader

        empty = _load_fixture("mail_empty.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=empty)

        port = GraphMailReader(transport=httpx.MockTransport(handler))

        messages = await port.list_messages(_ctx(), limit=10)

        assert messages == []

    @pytest.mark.asyncio
    async def test_list_messages_maps_every_field_from_the_graph_payload(
        self,
    ) -> None:
        """Triangulation: every `MailMessage` field is populated from the
        REAL Graph message shape, not a hardcoded stub."""

        from app.integrations.adapters.microsoft365.ports import GraphMailReader

        single_page = _load_fixture("mail_page_2.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=single_page)

        port = GraphMailReader(transport=httpx.MockTransport(handler))

        messages = await port.list_messages(_ctx(), limit=10)

        assert len(messages) == 1
        message = messages[0]
        assert message.external_id == "mail-3"
        assert message.subject == "Confirmación de entrega"
        assert message.sender == "diana.paez@contoso.com"
        assert message.recipients == (
            "ana.torres@contoso.com",
            "carlos.ruiz@contoso.com",
        )
        assert message.snippet == "Confirmamos la entrega del módulo de tareas."
        assert message.body_text == (
            "Confirmamos la entrega del módulo de tareas para revisión."
        )
        assert message.received_at.year == 2026
        assert message.received_at.month == 7
        assert message.received_at.day == 8

    def test_mail_reader_is_wired_into_the_adapter_mail_capability(self) -> None:
        """The adapter's `port_for(Capability.mail)` resolves to a REAL
        `GraphMailReader`, not `None` (spec.md "Lectura de correo...")."""

        from app.integrations.adapters.microsoft365.adapter import Microsoft365Adapter
        from app.integrations.adapters.microsoft365.ports import GraphMailReader
        from app.integrations.ports import Capability

        adapter = Microsoft365Adapter()

        port = adapter.port_for(Capability.mail)

        assert isinstance(port, GraphMailReader)


# ---------------------------------------------------------------------------
# Lote 5 — Calendario: `CalendarReaderPort`
# ---------------------------------------------------------------------------


class TestCalendarPort:
    @pytest.mark.asyncio
    async def test_list_events_aggregates_dtos_from_two_pages_respecting_limit(
        self,
    ) -> None:
        """Scenario: Resultados dentro de la ventana, multi-página (M365-R4,
        calendario) — `@odata.nextLink` is followed across a second, inline
        page and every DTO is aggregated."""

        from app.integrations.adapters.microsoft365.ports import GraphCalendarReader
        from app.integrations.dtos import CalendarEvent

        page_1 = _load_fixture("calendar_page_1.json")
        page_2 = {
            "@odata.context": page_1["@odata.context"],
            "value": [
                {
                    "id": "event-3",
                    "subject": "Retro del sprint",
                    "start": {"dateTime": "2026-07-22T14:00:00.0000000", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-07-22T15:00:00.0000000", "timeZone": "UTC"},
                    "organizer": {
                        "emailAddress": {"name": "Ana Torres", "address": "ana.torres@contoso.com"}
                    },
                    "attendees": [],
                    "location": None,
                }
            ],
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.params.get("$skip") == "2":
                return httpx.Response(200, json=page_2)
            assert request.url.path == "/v1.0/me/calendarView"
            assert "startDateTime" in request.url.params
            assert "endDateTime" in request.url.params
            return httpx.Response(200, json=page_1)

        port = GraphCalendarReader(transport=httpx.MockTransport(handler))

        events = await port.list_events(_ctx(), limit=10)

        assert [e.external_id for e in events] == ["event-1", "event-2", "event-3"]
        assert all(isinstance(e, CalendarEvent) for e in events)

    @pytest.mark.asyncio
    async def test_list_events_returns_empty_list_without_error(self) -> None:
        """Scenario: Sin resultados en la ventana — an empty `value` never
        raises (M365-R4, calendario)."""

        from app.integrations.adapters.microsoft365.ports import GraphCalendarReader

        empty = _load_fixture("calendar_empty.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=empty)

        port = GraphCalendarReader(transport=httpx.MockTransport(handler))

        events = await port.list_events(_ctx(), limit=10)

        assert events == []

    @pytest.mark.asyncio
    async def test_list_events_maps_every_field_from_the_graph_payload(self) -> None:
        """Triangulation: organizer/attendees/location map from the REAL
        Graph event shape — including a `location: null` event mapping to
        `None`, not a crash."""

        from app.integrations.adapters.microsoft365.ports import GraphCalendarReader

        page_1 = _load_fixture("calendar_page_1.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"value": page_1["value"]})

        port = GraphCalendarReader(transport=httpx.MockTransport(handler))

        events = await port.list_events(_ctx(), limit=10)

        assert len(events) == 2
        first, second = events
        assert first.external_id == "event-1"
        assert first.title == "Reunión de seguimiento del proyecto"
        assert first.organizer == "ana.torres@contoso.com"
        assert first.attendees == ("carlos.ruiz@contoso.com",)
        assert first.location == "Sala virtual"
        assert first.starts_at.year == 2026
        assert first.starts_at.hour == 15

        assert second.external_id == "event-2"
        assert second.attendees == ()
        assert second.location is None

    def test_calendar_reader_is_wired_into_the_adapter_calendar_capability(
        self,
    ) -> None:
        """The adapter's `port_for(Capability.calendar)` resolves to a REAL
        `GraphCalendarReader`, not `None`."""

        from app.integrations.adapters.microsoft365.adapter import Microsoft365Adapter
        from app.integrations.adapters.microsoft365.ports import GraphCalendarReader
        from app.integrations.ports import Capability

        adapter = Microsoft365Adapter()

        port = adapter.port_for(Capability.calendar)

        assert isinstance(port, GraphCalendarReader)


# ---------------------------------------------------------------------------
# Lote 6 — Tareas Planner: `ExternalTaskReaderPort`
# ---------------------------------------------------------------------------


class TestPlannerPort:
    @pytest.mark.asyncio
    async def test_list_tasks_maps_dtos_and_filters_by_the_default_since_window(
        self,
    ) -> None:
        """Scenario: Tenant con Planner — every fixture task maps to a
        DTO; the default (no explicit `since`) 30-day window is applied
        CLIENT-side by `createdDateTime` (Graph does not support a
        server-side date filter on this endpoint, spec.md)."""

        from app.integrations.adapters.microsoft365.ports import GraphExternalTaskReader
        from app.integrations.dtos import ExternalTask

        fixture = _load_fixture("planner_tasks.json")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1.0/me/planner/tasks"
            return httpx.Response(200, json=fixture)

        port = GraphExternalTaskReader(transport=httpx.MockTransport(handler))

        tasks = await port.list_tasks(_ctx(), limit=10)

        # planner-task-3 was created 2025-01-01 — outside the default 30-day
        # window from "today" — filtered out client-side.
        assert [t.external_id for t in tasks] == ["planner-task-1", "planner-task-2"]
        assert all(isinstance(t, ExternalTask) for t in tasks)

        in_progress, completed = tasks
        assert in_progress.title == "Actualizar la documentación de la API"
        assert in_progress.status == "in_progress"
        assert in_progress.assignee == "user-guid-1"
        assert in_progress.due_at is not None
        assert in_progress.due_at.year == 2026 and in_progress.due_at.month == 7

        assert completed.status == "completed"
        assert completed.assignee is None
        assert completed.due_at is None

    @pytest.mark.asyncio
    async def test_list_tasks_with_an_explicit_since_includes_older_tasks(
        self,
    ) -> None:
        """Triangulation: an explicit `since` far enough in the past
        includes `planner-task-3`, proving the filter really uses
        `since`, not a hardcoded window."""

        from app.integrations.adapters.microsoft365.ports import GraphExternalTaskReader

        fixture = _load_fixture("planner_tasks.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=fixture)

        port = GraphExternalTaskReader(transport=httpx.MockTransport(handler))

        tasks = await port.list_tasks(
            _ctx(), since=datetime(2024, 1, 1, tzinfo=UTC), limit=10
        )

        assert {t.external_id for t in tasks} == {
            "planner-task-1",
            "planner-task-2",
            "planner-task-3",
        }

    @pytest.mark.asyncio
    async def test_list_tasks_respects_limit_after_client_side_filtering(self) -> None:
        """`limit` truncates the CLIENT-side filtered result, not the raw
        Graph page."""

        from app.integrations.adapters.microsoft365.ports import GraphExternalTaskReader

        fixture = _load_fixture("planner_tasks.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=fixture)

        port = GraphExternalTaskReader(transport=httpx.MockTransport(handler))

        tasks = await port.list_tasks(_ctx(), limit=1)

        assert [t.external_id for t in tasks] == ["planner-task-1"]

    @pytest.mark.asyncio
    async def test_list_tasks_returns_empty_list_when_tenant_has_no_plans(
        self,
    ) -> None:
        """Scenario: Tenant sin Planner/Grupos M365 — an empty `value`
        never raises, it returns `[]` (spec.md, "NUNCA error")."""

        from app.integrations.adapters.microsoft365.ports import GraphExternalTaskReader

        empty = _load_fixture("planner_empty.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=empty)

        port = GraphExternalTaskReader(transport=httpx.MockTransport(handler))

        tasks = await port.list_tasks(_ctx(), limit=10)

        assert tasks == []

    def test_planner_reader_is_wired_into_the_adapter_external_tasks_capability(
        self,
    ) -> None:
        """The adapter's `port_for(Capability.external_tasks)` resolves to a
        REAL `GraphExternalTaskReader`, not `None`."""

        from app.integrations.adapters.microsoft365.adapter import Microsoft365Adapter
        from app.integrations.adapters.microsoft365.ports import (
            GraphExternalTaskReader,
        )
        from app.integrations.ports import Capability

        adapter = Microsoft365Adapter()

        port = adapter.port_for(Capability.external_tasks)

        assert isinstance(port, GraphExternalTaskReader)


# ---------------------------------------------------------------------------
# Lote 7 — Notas de reunión + degradación por consentimiento
# ---------------------------------------------------------------------------


class TestMeetingNotesPort:
    @pytest.mark.asyncio
    async def test_missing_scope_degrades_to_capability_unavailable_without_network(
        self,
    ) -> None:
        """Scenario: Consentimiento no otorgado degrada sin afectar el
        resto — the scope check happens BEFORE any HTTP call (design.md
        ADR #2, "introspección de scopes SIN RED")."""

        from app.integrations.adapters.microsoft365.ports import GraphMeetingNotesReader
        from app.shared.exceptions import AppException

        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={"value": []})

        port = GraphMeetingNotesReader(transport=httpx.MockTransport(handler))
        ctx = _ctx(scopes=())  # no OnlineMeetingTranscript.Read.All

        with pytest.raises(AppException) as excinfo:
            await port.list_notes(ctx, limit=10)

        assert excinfo.value.code == "capability_unavailable"
        assert call_count == 0

    @pytest.mark.asyncio
    async def test_granted_scope_returns_the_mapped_transcript_dto(self) -> None:
        """Scenario: Consentimiento otorgado — with the scope present, the
        transcript list + its content are fetched and mapped into a
        `MeetingNote`."""

        from app.integrations.adapters.microsoft365.ports import GraphMeetingNotesReader
        from app.integrations.dtos import MeetingNote

        granted = _load_fixture("transcript_granted.json")
        content = _load_fixture("transcript_content.json")["content"]

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/content"):
                assert "meeting-1" in request.url.path
                assert "transcript-1" in request.url.path
                return httpx.Response(200, text=content)
            return httpx.Response(200, json=granted)

        port = GraphMeetingNotesReader(transport=httpx.MockTransport(handler))
        ctx = _ctx(scopes=("OnlineMeetingTranscript.Read.All",))

        notes = await port.list_notes(ctx, limit=10)

        assert len(notes) == 1
        note = notes[0]
        assert isinstance(note, MeetingNote)
        assert note.external_id == "transcript-1"
        assert note.transcript == content
        assert note.occurred_at.year == 2026
        assert note.occurred_at.month == 7

    @pytest.mark.asyncio
    async def test_runtime_403_also_degrades_to_capability_unavailable(self) -> None:
        """Scenario (defense in depth): even with the scope claimed by the
        token, a live `403 Authorization_RequestDenied` from Graph (e.g.
        admin consent revoked after issuance) degrades the SAME way as the
        pre-flight check."""

        from app.integrations.adapters.microsoft365.ports import GraphMeetingNotesReader
        from app.shared.exceptions import AppException

        denied = _load_fixture("no_consent_403.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json=denied)

        port = GraphMeetingNotesReader(transport=httpx.MockTransport(handler))
        ctx = _ctx(scopes=("OnlineMeetingTranscript.Read.All",))

        with pytest.raises(AppException) as excinfo:
            await port.list_notes(ctx, limit=10)

        assert excinfo.value.code == "capability_unavailable"

    def test_meeting_notes_degradation_does_not_affect_other_capabilities(
        self,
    ) -> None:
        """Scenario (continuación): la degradación de `meeting_notes` no
        afecta correo, calendario ni tareas del MISMO adaptador — every
        other port is still wired independently."""

        from app.integrations.adapters.microsoft365.adapter import Microsoft365Adapter
        from app.integrations.adapters.microsoft365.ports import (
            GraphCalendarReader,
            GraphExternalTaskReader,
            GraphMailReader,
            GraphMeetingNotesReader,
        )
        from app.integrations.ports import Capability

        adapter = Microsoft365Adapter()

        assert isinstance(adapter.port_for(Capability.mail), GraphMailReader)
        assert isinstance(adapter.port_for(Capability.calendar), GraphCalendarReader)
        assert isinstance(
            adapter.port_for(Capability.external_tasks), GraphExternalTaskReader
        )
        assert isinstance(
            adapter.port_for(Capability.meeting_notes), GraphMeetingNotesReader
        )
