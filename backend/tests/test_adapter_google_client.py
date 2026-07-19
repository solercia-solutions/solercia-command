"""RED tests for `app/integrations/adapters/google/client.py` (change
16-adapter-google, specs/google-adapter/spec.md GA-R3/GA-R9).

Every test runs against `httpx.MockTransport` fixtures under
`tests/fixtures/google/` — ZERO real network in CI. Classes are grouped by
concern so `pytest -k` can target a single slice:
    TestGoogleClientBase        — paginación + TLS obligatorio
    TestGoogleClientResilience  — 401 refresh + 429/403 backoff + errores
    TestGoogleClientPaginationSecurity — divergencia estructural vs Graph
"""

import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.integrations.dtos import OAuthTokens
from app.integrations.ports import AccessContext

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "google"
_GMAIL_BASE_URL = "https://gmail.googleapis.com/gmail/v1"


def _load_fixture(name: str) -> dict:
    """Load a Google API response fixture by filename from
    `tests/fixtures/google/`."""

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
    """Build a real `Settings` instance with `GOOGLE_*` overrides for a test."""

    return Settings(**overrides)


async def _noop_sleep(_seconds: float) -> None:
    """Injectable `sleep` that never actually waits — resilience tests
    exercise the retry LOGIC, not real time (design.md, "sin espera real")."""


# ---------------------------------------------------------------------------
# Cliente base: paginación por `nextPageToken` + TLS obligatorio
# ---------------------------------------------------------------------------


class TestGoogleClientBase:
    def test_rejects_a_non_https_base_url(self) -> None:
        """Threat Matrix: TLS obligatorio — `GoogleClient` fails fast when
        its `base_url` is not `https://` (anti-SSRF/TLS, mismo criterio que
        `GraphClient._require_https`)."""

        from app.integrations.adapters.google.client import GoogleClient

        with pytest.raises(ValueError, match="base_url"):
            GoogleClient(_ctx(), base_url="http://gmail.googleapis.com/gmail/v1")

    @pytest.mark.asyncio
    async def test_paginate_follows_next_page_token_across_pages(self) -> None:
        """Scenario: Resultados dentro de la ventana, multi-página — two
        fixture pages chained by `nextPageToken` are fully aggregated."""

        from app.integrations.adapters.google.client import GoogleClient

        page_1 = _load_fixture("generic_page_1.json")
        page_2 = _load_fixture("generic_page_2.json")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.params.get("pageToken") == "generic-page-2-token":
                return httpx.Response(200, json=page_2)
            return httpx.Response(200, json=page_1)

        client = GoogleClient(
            _ctx(), base_url=_GMAIL_BASE_URL, transport=httpx.MockTransport(handler)
        )

        items = await client.paginate("/generic", params={}, items_key="items", limit=10)

        assert [item["id"] for item in items] == [
            "generic-item-1",
            "generic-item-2",
            "generic-item-3",
        ]

    @pytest.mark.asyncio
    async def test_paginate_single_page_without_next_token_returns_its_items(
        self,
    ) -> None:
        """A response with no `nextPageToken` terminates pagination after
        one page."""

        from app.integrations.adapters.google.client import GoogleClient

        payload = _load_fixture("generic_single_page.json")
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=payload)

        client = GoogleClient(
            _ctx(), base_url=_GMAIL_BASE_URL, transport=httpx.MockTransport(handler)
        )

        items = await client.paginate("/generic", params={}, items_key="items", limit=50)

        assert [item["id"] for item in items] == ["generic-solo-item"]
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_paginate_stops_once_limit_is_reached(self) -> None:
        """`limit` is respected even when the first page alone exceeds it —
        no extra page is fetched once enough items are already collected."""

        from app.integrations.adapters.google.client import GoogleClient

        page_1 = _load_fixture("generic_page_1.json")  # 2 items + nextPageToken
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=page_1)

        client = GoogleClient(
            _ctx(), base_url=_GMAIL_BASE_URL, transport=httpx.MockTransport(handler)
        )

        items = await client.paginate("/generic", params={}, items_key="items", limit=1)

        assert [item["id"] for item in items] == ["generic-item-1"]
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_paginate_cuts_off_at_max_pages_without_looping_forever(
        self,
    ) -> None:
        """A response that always returns another `nextPageToken`
        (adversarial/misbehaving server) is bounded by `GOOGLE_MAX_PAGES` —
        never an infinite loop."""

        from app.integrations.adapters.google.client import GoogleClient

        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(
                200,
                json={
                    "items": [{"id": f"forever-item-{call_count}"}],
                    "nextPageToken": "forever-token",
                },
            )

        settings = _settings(GOOGLE_MAX_PAGES=3)
        client = GoogleClient(
            _ctx(),
            base_url=_GMAIL_BASE_URL,
            transport=httpx.MockTransport(handler),
            settings=settings,
        )

        items = await client.paginate("/generic", params={}, items_key="items", limit=1000)

        assert call_count == 3
        assert len(items) == 3


# ---------------------------------------------------------------------------
# Divergencia estructural: `nextPageToken` es un token opaco, NUNCA una URL
# ---------------------------------------------------------------------------


class TestGoogleClientPaginationSecurity:
    @pytest.mark.asyncio
    async def test_pagination_never_follows_a_response_supplied_host_only_a_token(
        self,
    ) -> None:
        """Divergencia frente al `@odata.nextLink` de Graph (una URL
        completa que el cliente debe seguir): el `nextPageToken` de Google
        es un STRING OPACO devuelto como valor del query param `pageToken`
        sobre el MISMO `base_url` configurado — incluso un token adversario
        que PARECE una URL se envía como valor literal, nunca decide el
        host de la siguiente solicitud (no hay "next link" que fijar por
        host: la seguridad es estructural aquí, no una validación en
        runtime)."""

        from app.integrations.adapters.google.client import GoogleClient

        requested_hosts: set[str | None] = set()
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            requested_hosts.add(request.url.host)
            if call_count == 1:
                return httpx.Response(
                    200,
                    json={
                        "items": [{"id": "item-1"}],
                        "nextPageToken": "https://evil.example.com/steal",
                    },
                )
            assert request.url.params.get("pageToken") == "https://evil.example.com/steal"
            return httpx.Response(200, json={"items": [{"id": "item-2"}]})

        client = GoogleClient(
            _ctx(), base_url=_GMAIL_BASE_URL, transport=httpx.MockTransport(handler)
        )

        items = await client.paginate("/generic", params={}, items_key="items", limit=10)

        assert requested_hosts == {"gmail.googleapis.com"}
        assert [item["id"] for item in items] == ["item-1", "item-2"]


# ---------------------------------------------------------------------------
# Resiliencia: 401 refresh + 429/403 backoff + errores
# ---------------------------------------------------------------------------


class TestGoogleClientResilience:
    @pytest.mark.asyncio
    async def test_401_triggers_refresh_once_and_retries_successfully(self) -> None:
        """Scenario: 401 dispara refresh y reintento único (GA-R3) — a 401
        makes the client refresh the token exactly once and retry the SAME
        request, which then succeeds."""

        from app.integrations.adapters.google.client import GoogleClient

        unauthorized = _load_fixture("error_401.json")
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
                external_account_id="ana.torres@example.com",
                access_token="fresh-access-token",
                refresh_token="fresh-refresh-token",
                expires_at=None,
                scopes=("gmail.readonly",),
            )

        sink_calls: list[OAuthTokens] = []

        async def on_tokens_refreshed(tokens: OAuthTokens) -> None:
            sink_calls.append(tokens)

        ctx = _ctx(on_tokens_refreshed=on_tokens_refreshed)
        client = GoogleClient(
            ctx,
            base_url=_GMAIL_BASE_URL,
            transport=httpx.MockTransport(handler),
            sleep=_noop_sleep,
            refresh=refresh,
        )

        items = await client.paginate("/generic", params={}, items_key="items", limit=10)

        assert [item["id"] for item in items] == ["after-retry-item"]
        assert refresh_calls == 1
        assert seen_tokens == ["Bearer test-access-token", "Bearer fresh-access-token"]
        assert sink_calls[0].access_token == "fresh-access-token"

    @pytest.mark.asyncio
    async def test_revoked_refresh_token_raises_controlled_error_without_looping(
        self,
    ) -> None:
        """A refresh that itself fails (revoked token) raises a controlled
        reconnection error and NEVER loops (only ONE 401 request is ever
        made)."""

        from app.integrations.adapters.google.client import GoogleClient
        from app.shared.exceptions import AppException

        unauthorized = _load_fixture("error_401.json")
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(401, json=unauthorized)

        async def revoked_refresh(refresh_token: str) -> None:
            raise RuntimeError("invalid_grant: refresh token revoked")

        client = GoogleClient(
            _ctx(),
            base_url=_GMAIL_BASE_URL,
            transport=httpx.MockTransport(handler),
            sleep=_noop_sleep,
            refresh=revoked_refresh,
        )

        with pytest.raises(AppException) as excinfo:
            await client.paginate("/generic", params={}, items_key="items", limit=10)

        assert excinfo.value.code == "oauth_token_invalid"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_429_honors_retry_after_and_succeeds(self) -> None:
        """Scenario: 429 respeta backoff (GA-R3) — a `429` with
        `Retry-After` makes the client sleep at least that long (via the
        injected `sleep`) before retrying, then completes on success."""

        from app.integrations.adapters.google.client import GoogleClient

        throttled = _load_fixture("error_429.json")
        ok = _load_fixture("ok_after_retry.json")
        sleep_calls: list[float] = []
        call_count = 0

        async def spy_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(429, json=throttled, headers={"Retry-After": "2"})
            return httpx.Response(200, json=ok)

        client = GoogleClient(
            _ctx(),
            base_url=_GMAIL_BASE_URL,
            transport=httpx.MockTransport(handler),
            sleep=spy_sleep,
        )

        items = await client.paginate("/generic", params={}, items_key="items", limit=10)

        assert [item["id"] for item in items] == ["after-retry-item"]
        assert sleep_calls == [2.0]
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_403_rate_limit_exceeded_also_backs_off_and_retries(self) -> None:
        """`403 rateLimitExceeded`/`userRateLimitExceeded` is cuota, not a
        permission failure — it backs off exactly like a `429`, NOT
        `capability_unavailable`."""

        from app.integrations.adapters.google.client import GoogleClient

        throttled = _load_fixture("error_403_rate_limit.json")
        ok = _load_fixture("ok_after_retry.json")
        sleep_calls: list[float] = []
        call_count = 0

        async def spy_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(403, json=throttled)
            return httpx.Response(200, json=ok)

        client = GoogleClient(
            _ctx(),
            base_url=_GMAIL_BASE_URL,
            transport=httpx.MockTransport(handler),
            sleep=spy_sleep,
        )

        items = await client.paginate("/generic", params={}, items_key="items", limit=10)

        assert [item["id"] for item in items] == ["after-retry-item"]
        assert len(sleep_calls) == 1
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_429_beyond_max_retries_raises_controlled_error(self) -> None:
        """`429` repeated past `GOOGLE_MAX_RETRIES` raises a controlled
        error instead of retrying forever."""

        from app.integrations.adapters.google.client import GoogleClient
        from app.shared.exceptions import AppException

        throttled = _load_fixture("error_429.json")
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(429, json=throttled, headers={"Retry-After": "1"})

        settings = _settings(GOOGLE_MAX_RETRIES=2)
        client = GoogleClient(
            _ctx(),
            base_url=_GMAIL_BASE_URL,
            transport=httpx.MockTransport(handler),
            sleep=_noop_sleep,
            settings=settings,
        )

        with pytest.raises(AppException) as excinfo:
            await client.paginate("/generic", params={}, items_key="items", limit=10)

        assert excinfo.value.code == "provider_throttled"
        assert call_count == 1 + settings.GOOGLE_MAX_RETRIES

    @pytest.mark.asyncio
    async def test_403_drive_permission_denied_raises_capability_unavailable(
        self,
    ) -> None:
        """Scenario: falta de permiso Drive se reporta como capacidad no
        disponible — a `403` WITHOUT a quota `reason` never backs off, it
        raises immediately."""

        from app.integrations.adapters.google.client import GoogleClient
        from app.shared.exceptions import AppException

        denied = _load_fixture("error_403_drive_permission.json")
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(403, json=denied)

        client = GoogleClient(
            _ctx(),
            base_url=_GMAIL_BASE_URL,
            transport=httpx.MockTransport(handler),
            sleep=_noop_sleep,
        )

        with pytest.raises(AppException) as excinfo:
            await client.paginate("/generic", params={}, items_key="items", limit=10)

        assert excinfo.value.code == "capability_unavailable"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_no_token_leaks_in_caplog_or_exception_message(self, caplog) -> None:
        """Neither the access token nor the refresh token used in a request
        that fails ever appears in a log record or in the raised
        exception's message (Threat Matrix, "sin fuga de tokens")."""

        from app.integrations.adapters.google.client import GoogleClient
        from app.shared.exceptions import AppException

        unauthorized = _load_fixture("error_401.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json=unauthorized)

        async def revoked_refresh(refresh_token: str) -> None:
            raise RuntimeError("invalid_grant")

        ctx = _ctx(
            access_token="super-secret-access-token",
            refresh_token="super-secret-refresh-token",
        )
        client = GoogleClient(
            ctx,
            base_url=_GMAIL_BASE_URL,
            transport=httpx.MockTransport(handler),
            sleep=_noop_sleep,
            refresh=revoked_refresh,
        )

        with caplog.at_level("DEBUG"):
            with pytest.raises(AppException) as excinfo:
                await client.paginate("/generic", params={}, items_key="items", limit=10)

        assert "super-secret-access-token" not in str(excinfo.value)
        assert "super-secret-refresh-token" not in str(excinfo.value)
        assert "super-secret-access-token" not in caplog.text
        assert "super-secret-refresh-token" not in caplog.text

    @pytest.mark.asyncio
    async def test_4xx_other_than_401_403_429_raises_a_non_retryable_domain_error(
        self, caplog
    ) -> None:
        """A `400` (solicitud inválida) es un error DE DOMINIO propio
        (`provider_request_failed`), distinto del `provider_unavailable`
        reintentable — y queda logueado (status + cuerpo truncado, sin
        tokens) para diagnóstico."""

        from app.integrations.adapters.google.client import GoogleClient
        from app.shared.exceptions import AppException

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"message": "bad request"}})

        client = GoogleClient(
            _ctx(access_token="super-secret-access-token"),
            base_url=_GMAIL_BASE_URL,
            transport=httpx.MockTransport(handler),
            sleep=_noop_sleep,
        )

        with caplog.at_level("WARNING"):
            with pytest.raises(AppException) as excinfo:
                await client.paginate("/generic", params={}, items_key="items", limit=10)

        assert excinfo.value.code == "provider_request_failed"
        assert excinfo.value.status_code != 503
        assert "400" in caplog.text
        assert "super-secret-access-token" not in caplog.text

    @pytest.mark.asyncio
    async def test_5xx_raises_the_retryable_provider_unavailable_error(
        self, caplog
    ) -> None:
        """Un `5xx` (falla transitoria del lado de Google) mapea a
        `provider_unavailable` (reintentable), distinto del `400` de
        arriba."""

        from app.integrations.adapters.google.client import GoogleClient
        from app.shared.exceptions import AppException

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": {"message": "unavailable"}})

        client = GoogleClient(
            _ctx(),
            base_url=_GMAIL_BASE_URL,
            transport=httpx.MockTransport(handler),
            sleep=_noop_sleep,
        )

        with caplog.at_level("WARNING"):
            with pytest.raises(AppException) as excinfo:
                await client.paginate("/generic", params={}, items_key="items", limit=10)

        assert excinfo.value.code == "provider_unavailable"
        assert "503" in caplog.text

    @pytest.mark.asyncio
    async def test_429_retry_after_beyond_the_ceiling_sleeps_at_most_the_max(
        self,
    ) -> None:
        """Un `Retry-After` abusivo (ej. 3600s) NUNCA hace dormir al
        cliente más de `GOOGLE_MAX_BACKOFF_SECONDS`."""

        from app.integrations.adapters.google.client import GoogleClient

        throttled = _load_fixture("error_429.json")
        ok = _load_fixture("ok_after_retry.json")
        sleep_calls: list[float] = []
        call_count = 0

        async def spy_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(429, json=throttled, headers={"Retry-After": "3600"})
            return httpx.Response(200, json=ok)

        settings = _settings(GOOGLE_MAX_BACKOFF_SECONDS=30.0)
        client = GoogleClient(
            _ctx(),
            base_url=_GMAIL_BASE_URL,
            transport=httpx.MockTransport(handler),
            sleep=spy_sleep,
            settings=settings,
        )

        items = await client.paginate("/generic", params={}, items_key="items", limit=10)

        assert [item["id"] for item in items] == ["after-retry-item"]
        assert sleep_calls == [30.0]

    @pytest.mark.asyncio
    async def test_get_issues_a_single_non_paginated_request_with_bearer_auth(
        self,
    ) -> None:
        """`client.get(...)` — used by ports that fetch ONE resource
        directly (a message by id, a Doc export) — applies the SAME
        resilience boundary as `paginate`, sending the `Authorization:
        Bearer` header on every request."""

        from app.integrations.adapters.google.client import GoogleClient

        seen_auth: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_auth.append(request.headers["Authorization"])
            return httpx.Response(200, text="contenido exportado")

        client = GoogleClient(
            _ctx(access_token="single-resource-token"),
            base_url=_GMAIL_BASE_URL,
            transport=httpx.MockTransport(handler),
        )

        response = await client.get("/files/doc-1/export", params={"mimeType": "text/plain"})

        assert response.text == "contenido exportado"
        assert seen_auth == ["Bearer single-resource-token"]
