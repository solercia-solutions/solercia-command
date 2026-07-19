"""OAuth handshake against Entra ID (Azure AD) v2.0 endpoints (change
15-adapter-microsoft365, spec.md "Handshake OAuth delegado de Entra ID").

Confidential-client flow (``client_secret``); PKCE is deliberately DEFERRED
(design.md ADR #4 — the 14's ``state_store`` does not persist a
``code_verifier`` yet). ``state`` single-use (the 14's ``state_store.pop``)
plus ``client_secret`` give an equivalent CSRF/replay boundary for this
wave.

``OAuthTokens.external_account_id`` is the token response's ``id_token``
``oid`` claim (design.md ADR #5 — stable across a UPN rename, unlike the
display name). The ``id_token``'s signature is NOT independently
re-verified here: both `exchange_code`/`refresh` are server-to-server TLS
calls straight to Microsoft's own ``/token`` endpoint (never handled by
the browser), the same trust boundary the access/refresh token VALUES
already rely on.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.microsoft365 import errors
from app.integrations.dtos import OAuthTokens

# Scopes delegados por defecto (spec.md "Handshake OAuth delegado de Entra
# ID": "openid profile email offline_access User.Read` + los de cada
# capacidad"). `OnlineMeetingTranscript.Read.All` NUNCA entra aquí: es
# opt-in por conector (design.md ADR #1).
DEFAULT_DELEGATED_SCOPES: tuple[str, ...] = (
    "openid",
    "profile",
    "email",
    "offline_access",
    "User.Read",
    "Mail.Read",
    "Calendars.Read",
    "Tasks.Read",
    "OnlineMeetings.Read",
)


def _effective_scopes(scopes: Sequence[str] | None) -> Sequence[str]:
    """``scopes`` unchanged when explicit; otherwise the default delegated
    set — never a request with ``scope=`` empty."""

    return scopes if scopes else DEFAULT_DELEGATED_SCOPES


def _authorize_endpoint(settings: Settings, tenant: str) -> str:
    return f"{settings.M365_LOGIN_BASE_URL}/{tenant}/oauth2/v2.0/authorize"


def _token_endpoint(settings: Settings, tenant: str) -> str:
    return f"{settings.M365_LOGIN_BASE_URL}/{tenant}/oauth2/v2.0/token"


def authorize_url(
    state: str,
    redirect_uri: str,
    scopes: Sequence[str],
    *,
    settings: Settings = default_settings,
) -> str:
    """Build the Entra ID authorize URL for ``state``/``redirect_uri``.

    Uses ``settings.M365_TENANT`` (default ``organizations``) — NEVER a
    tenant taken from caller input — so the endpoint's host+path stay fully
    derived from configuration (anti-SSRF/host fijo, mirrors ``client.py``'s
    boundary). Empty ``scopes`` assembles :data:`DEFAULT_DELEGATED_SCOPES`
    instead of requesting an empty scope; explicit scopes are respected
    as-is."""

    params = {
        "client_id": settings.M365_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": " ".join(_effective_scopes(scopes)),
        "state": state,
    }
    endpoint = _authorize_endpoint(settings, settings.M365_TENANT)
    return f"{endpoint}?{urlencode(params)}"


async def exchange_code(
    code: str,
    redirect_uri: str,
    *,
    settings: Settings = default_settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> OAuthTokens:
    """Exchange an authorization ``code`` for tokens (``authorization_code``
    grant)."""

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": settings.M365_CLIENT_ID,
        "client_secret": settings.M365_CLIENT_SECRET,
    }
    return await _post_token(data, settings=settings, transport=transport)


async def refresh(
    refresh_token: str,
    *,
    settings: Settings = default_settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> OAuthTokens:
    """Exchange a ``refresh_token`` for a fresh set of tokens
    (``refresh_token`` grant)."""

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.M365_CLIENT_ID,
        "client_secret": settings.M365_CLIENT_SECRET,
    }
    return await _post_token(data, settings=settings, transport=transport)


async def _post_token(
    data: dict[str, str],
    *,
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None,
) -> OAuthTokens:
    endpoint = _token_endpoint(settings, settings.M365_TENANT)
    async with httpx.AsyncClient(
        timeout=settings.M365_TIMEOUT_SECONDS, transport=transport
    ) as http_client:
        response = await http_client.post(endpoint, data=data)

    if response.status_code >= 400:
        # Never propagate the provider's raw body — it may echo the
        # `refresh_token`/`code` the request sent (Threat Matrix, "sin
        # fuga de tokens").
        raise errors.oauth_token_invalid()

    payload: dict[str, Any] = response.json()
    return _tokens_from_payload(payload)


def _tokens_from_payload(payload: dict[str, Any]) -> OAuthTokens:
    id_token = payload.get("id_token")
    claims: dict[str, Any] = (
        jwt.decode(id_token, options={"verify_signature": False}) if id_token else {}
    )
    oid = claims.get("oid")
    if not oid:
        raise errors.oauth_token_invalid()

    expires_in = payload.get("expires_in")
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=int(expires_in))
        if expires_in is not None
        else None
    )
    scope_str = payload.get("scope") or ""
    scopes = tuple(scope_str.split()) if scope_str else ()

    return OAuthTokens(
        external_account_id=str(oid),
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=expires_at,
        scopes=scopes,
    )
