"""RED tests for `app/integrations/adapters/google/oauth.py` (change
16-adapter-google, specs/google-adapter/spec.md GA-R2).

`exchange_code`/`refresh` run against `httpx.MockTransport` fixtures under
`tests/fixtures/google/` — ZERO real network in CI.
"""

import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "google"


def _load_fixture(name: str) -> dict:
    """Load a Google API response fixture by filename from
    `tests/fixtures/google/`."""

    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _settings(**overrides) -> Settings:
    """Build a real `Settings` instance with `GOOGLE_*` overrides for a test."""

    return Settings(**overrides)


class TestAuthorizeUrl:
    def test_authorize_url_targets_googles_authorization_endpoint(self) -> None:
        """La URL generada apunta al endpoint de autorización de Google
        configurado, con `client_id`/`redirect_uri`/`state` propios."""

        from app.integrations.adapters.google import oauth

        settings = _settings(GOOGLE_OAUTH_CLIENT_ID="client-abc")

        url = oauth.authorize_url(
            "state-1",
            "https://app.test/callback",
            ["https://www.googleapis.com/auth/gmail.readonly"],
            settings=settings,
        )

        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        assert "state=state-1" in url
        assert "client_id=client-abc" in url
        assert "redirect_uri=https%3A%2F%2Fapp.test%2Fcallback" in url

    def test_authorize_url_requests_offline_access_and_consent_to_get_a_refresh_token(
        self,
    ) -> None:
        """Data Flow: `access_type=offline` + `prompt=consent` garantizan
        que Google emita un `refresh_token` en el primer canje."""

        from app.integrations.adapters.google import oauth

        settings = _settings(GOOGLE_OAUTH_CLIENT_ID="client-abc")

        url = oauth.authorize_url(
            "state-1", "https://app.test/callback", ["openid"], settings=settings
        )

        assert "access_type=offline" in url
        assert "prompt=consent" in url

    def test_authorize_url_only_ever_contains_readonly_scopes(self) -> None:
        """Scenario: Scopes solicitados son de solo lectura — el default
        ensamblado cuando el caller no pasa scopes es EXCLUSIVAMENTE
        `*.readonly`/`openid`/`email`/`profile`, nunca de escritura."""

        from app.integrations.adapters.google import oauth

        settings = _settings(GOOGLE_OAUTH_CLIENT_ID="client-abc")

        url = oauth.authorize_url(
            "state-1", "https://app.test/callback", [], settings=settings
        )

        assert "gmail.readonly" in url
        assert "calendar.readonly" in url
        assert "drive.readonly" in url
        assert "gmail.modify" not in url
        assert "gmail.send" not in url
        assert "calendar.events" not in url

    def test_authorize_url_assembles_default_readonly_scopes_when_none_given(
        self,
    ) -> None:
        """4R-style: un conector sin scopes configurados (`scopes=[]`)
        NUNCA debe pedir `scope=` vacío — se ensambla el set de solo
        lectura por defecto del adaptador."""

        from app.integrations.adapters.google import oauth

        settings = _settings(GOOGLE_OAUTH_CLIENT_ID="client-abc")

        url = oauth.authorize_url(
            "state-1", "https://app.test/callback", [], settings=settings
        )

        assert "scope=" in url
        assert "scope=&" not in url
        assert not url.rstrip("&").endswith("scope=")

    def test_authorize_url_respects_explicit_scopes_when_the_caller_passes_some(
        self,
    ) -> None:
        """Un conector CON scopes explícitos los respeta tal cual, sin
        mezclarlos con el default."""

        from app.integrations.adapters.google import oauth

        settings = _settings(GOOGLE_OAUTH_CLIENT_ID="client-abc")

        url = oauth.authorize_url(
            "state-1",
            "https://app.test/callback",
            ["openid", "email"],
            settings=settings,
        )

        assert "scope=openid+email" in url
        assert "gmail.readonly" not in url


class TestExchangeCode:
    @pytest.mark.asyncio
    async def test_exchange_code_returns_tokens_with_the_email_as_external_account_id(
        self,
    ) -> None:
        """Scenario: Canje de código devuelve el correo como identidad —
        `OAuthTokens.external_account_id` es el `email` de `userinfo`, NO
        un `sub`/`oid` opaco (decisión #4 del design)."""

        from app.integrations.adapters.google import oauth

        token_payload = _load_fixture("oauth_token_exchange.json")
        userinfo_payload = _load_fixture("oauth_userinfo.json")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                assert request.method == "POST"
                return httpx.Response(200, json=token_payload)
            assert request.url.host == "openidconnect.googleapis.com"
            assert request.headers["Authorization"] == "Bearer google-access-token-1"
            return httpx.Response(200, json=userinfo_payload)

        tokens = await oauth.exchange_code(
            "auth-code-1",
            "https://app.test/callback",
            transport=httpx.MockTransport(handler),
        )

        assert tokens.external_account_id == "ana.torres@example.com"
        assert tokens.access_token == "google-access-token-1"
        assert tokens.refresh_token == "google-refresh-token-1"
        assert tokens.expires_at is not None
        assert "https://www.googleapis.com/auth/gmail.readonly" in tokens.scopes

    @pytest.mark.asyncio
    async def test_exchange_code_posts_the_authorization_code_grant(self) -> None:
        """Triangulation: el `POST` al endpoint de token usa
        `grant_type=authorization_code` con el `code` recibido — prueba que
        el payload real se construye, no un stub fijo."""

        from app.integrations.adapters.google import oauth

        token_payload = _load_fixture("oauth_token_exchange.json")
        userinfo_payload = _load_fixture("oauth_userinfo.json")
        seen_data: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                seen_data.update(dict(httpx.QueryParams(request.content.decode())))
                return httpx.Response(200, json=token_payload)
            return httpx.Response(200, json=userinfo_payload)

        await oauth.exchange_code(
            "auth-code-XYZ",
            "https://app.test/callback",
            transport=httpx.MockTransport(handler),
        )

        assert seen_data["grant_type"] == "authorization_code"
        assert seen_data["code"] == "auth-code-XYZ"
        assert seen_data["redirect_uri"] == "https://app.test/callback"


class TestRefresh:
    @pytest.mark.asyncio
    async def test_refresh_with_a_rotated_refresh_token_returns_the_new_one(
        self,
    ) -> None:
        """Cuando Google SÍ re-emite `refresh_token`, el `OAuthTokens`
        resultante lo refleja."""

        from app.integrations.adapters.google import oauth

        token_payload = _load_fixture("oauth_refresh_with_token.json")
        userinfo_payload = _load_fixture("oauth_userinfo.json")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                return httpx.Response(200, json=token_payload)
            return httpx.Response(200, json=userinfo_payload)

        tokens = await oauth.refresh(
            "original-refresh-token", transport=httpx.MockTransport(handler)
        )

        assert tokens.access_token == "google-access-token-rotated"
        assert tokens.refresh_token == "google-refresh-token-rotated"
        assert tokens.external_account_id == "ana.torres@example.com"

    @pytest.mark.asyncio
    async def test_refresh_without_a_new_refresh_token_keeps_the_previous_one(
        self,
    ) -> None:
        """GOTCHA de Google (design.md): el `refresh_token` grant NO
        re-emite `refresh_token` en la respuesta con frecuencia — cuando
        está ausente, el `OAuthTokens` resultante CONSERVA el
        `refresh_token` que se usó para pedir el refresh, en vez de perder
        la credencial (lo que forzaría una reconexión innecesaria)."""

        from app.integrations.adapters.google import oauth

        token_payload = _load_fixture("oauth_refresh_without_token.json")
        assert "refresh_token" not in token_payload  # fixture guard
        userinfo_payload = _load_fixture("oauth_userinfo.json")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                return httpx.Response(200, json=token_payload)
            return httpx.Response(200, json=userinfo_payload)

        tokens = await oauth.refresh(
            "the-original-refresh-token", transport=httpx.MockTransport(handler)
        )

        assert tokens.access_token == "google-access-token-rotated-again"
        assert tokens.refresh_token == "the-original-refresh-token"

    @pytest.mark.asyncio
    async def test_no_token_leaks_in_caplog_or_exception_message_for_oauth(
        self, caplog
    ) -> None:
        """Threat Matrix: un rechazo del endpoint de token nunca hace
        aparecer el `refresh_token` usado en la solicitud, en un log ni en
        el mensaje de la excepción lanzada."""

        from app.integrations.adapters.google import oauth
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

        assert excinfo.value.code == "oauth_token_invalid"
        assert "super-secret-refresh-token" not in str(excinfo.value)
        assert "super-secret-refresh-token" not in caplog.text

    @pytest.mark.asyncio
    async def test_userinfo_endpoint_rejection_also_raises_a_controlled_error(
        self,
    ) -> None:
        """Si el canje de token funciona pero `userinfo` falla, el
        adaptador no deja escapar un `KeyError`/excepción cruda — mapea al
        mismo error de reconexión controlado."""

        from app.integrations.adapters.google import oauth
        from app.shared.exceptions import AppException

        token_payload = _load_fixture("oauth_token_exchange.json")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                return httpx.Response(200, json=token_payload)
            return httpx.Response(401, json={"error": "invalid_token"})

        with pytest.raises(AppException) as excinfo:
            await oauth.exchange_code(
                "auth-code-1",
                "https://app.test/callback",
                transport=httpx.MockTransport(handler),
            )

        assert excinfo.value.code == "oauth_token_invalid"
