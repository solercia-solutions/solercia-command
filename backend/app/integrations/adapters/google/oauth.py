"""OAuth 2.0 handshake against Google's own endpoints (change
16-adapter-google, spec.md "Handshake OAuth de Google mapeado a
OAuthTokens").

Plain authorization-code flow (``client_secret``, PKCE deliberately
deferred — same rationale as the 15's ADR #4: the 14's ``state_store``
does not persist a ``code_verifier`` yet). ``access_type=offline`` +
``prompt=consent`` on the authorize URL are what make Google actually
issue a ``refresh_token`` on the FIRST code exchange (design.md Data Flow).

``OAuthTokens.external_account_id`` is the connected account's EMAIL,
fetched from Google's ``userinfo`` endpoint with the fresh access token —
NOT an opaque ``sub``/``oid`` (design.md decision #4: identidad estable y
legible del ``ConnectedAccount``, consistente con
``UNIQUE(connector_id, external_account_id)`` del 14). This is a
DELIBERATE divergence from the 15's Entra ID ``oid``-from-``id_token``
approach — Google's own userinfo response is the simplest source of a
stable, human-legible identity here, and costs one extra request per
exchange/refresh (not a design gap: the 15's design.md itself notes
Google's own ADR differs, see design.md Architecture Decisions table).
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.google import errors
from app.integrations.dtos import OAuthTokens

# Scopes de solo lectura por defecto (spec.md "Handshake OAuth de Google...
# scopes exclusivamente *.readonly"): identidad (openid/email/profile) + una
# capacidad por puerto declarado (mail/calendar/meeting_notes). Ningún scope
# de escritura entra aquí NUNCA (GA-R8).
DEFAULT_READONLY_SCOPES: tuple[str, ...] = (
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
)


def _effective_scopes(scopes: Sequence[str] | None) -> Sequence[str]:
    """``scopes`` unchanged when explicit; otherwise the default readonly
    set — never a request with ``scope=`` empty."""

    return scopes if scopes else DEFAULT_READONLY_SCOPES


def authorize_url(
    state: str,
    redirect_uri: str,
    scopes: Sequence[str],
    *,
    settings: Settings = default_settings,
) -> str:
    """Build Google's authorize URL for ``state``/``redirect_uri``.

    ``access_type=offline`` + ``prompt=consent`` (design.md Data Flow)
    guarantee Google returns a ``refresh_token`` on this FIRST exchange —
    without ``prompt=consent`` a previously-authorized user would only get
    one on their very first-ever consent. Empty ``scopes`` assembles
    :data:`DEFAULT_READONLY_SCOPES` instead of requesting an empty scope;
    explicit scopes are respected as-is."""

    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(_effective_scopes(scopes)),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{settings.GOOGLE_AUTHZ_BASE_URL}?{urlencode(params)}"


async def exchange_code(
    code: str,
    redirect_uri: str,
    *,
    settings: Settings = default_settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> OAuthTokens:
    """Exchange an authorization ``code`` for tokens (``authorization_code``
    grant), then resolve the connected account's email via ``userinfo``."""

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
    }
    payload = await _post_token(data, settings=settings, transport=transport)
    email = await _fetch_email(
        payload["access_token"], settings=settings, transport=transport
    )
    return _tokens_from_payload(
        payload, external_account_id=email, previous_refresh_token=None
    )


async def refresh(
    refresh_token: str,
    *,
    settings: Settings = default_settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> OAuthTokens:
    """Exchange a ``refresh_token`` for a fresh set of tokens
    (``refresh_token`` grant).

    GOTCHA (design.md): Google frequently does NOT re-issue a
    ``refresh_token`` on this grant — when absent, the returned
    :class:`OAuthTokens` keeps the SAME ``refresh_token`` this call was
    invoked with, instead of losing the credential and forcing an
    unnecessary reconnection."""

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
    }
    payload = await _post_token(data, settings=settings, transport=transport)
    email = await _fetch_email(
        payload["access_token"], settings=settings, transport=transport
    )
    return _tokens_from_payload(
        payload, external_account_id=email, previous_refresh_token=refresh_token
    )


async def _post_token(
    data: dict[str, str],
    *,
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(
        timeout=settings.GOOGLE_TIMEOUT_SECONDS, transport=transport
    ) as http_client:
        response = await http_client.post(settings.GOOGLE_TOKEN_BASE_URL, data=data)

    if response.status_code >= 400:
        # Never propagate the provider's raw body — it may echo the
        # `refresh_token`/`code` the request sent (Threat Matrix, "sin fuga
        # de tokens").
        raise errors.oauth_token_invalid()

    payload: dict[str, Any] = response.json()
    return payload


async def _fetch_email(
    access_token: str,
    *,
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None,
) -> str:
    """Resolve the connected account's email from Google's ``userinfo``
    endpoint using the just-issued ``access_token`` — NEVER accepted
    unverified (Threat Matrix: un correo sin verificar como identidad
    permitiría enlazar la cuenta conectada a un correo que su dueño real no
    controla; mismo criterio que el gate de ``email_verified`` en
    ``app/modules/auth/sso_service.py:159-160``). Google's OIDC ``userinfo``
    (``GOOGLE_USERINFO_BASE_URL`` por defecto) devuelve ``email_verified``;
    su ``userinfo`` v2 más antiguo devuelve ``verified_email`` en su lugar —
    ambas claves se aceptan, cualquiera que envíe el endpoint configurado."""

    async with httpx.AsyncClient(
        timeout=settings.GOOGLE_TIMEOUT_SECONDS, transport=transport
    ) as http_client:
        response = await http_client.get(
            settings.GOOGLE_USERINFO_BASE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if response.status_code >= 400:
        raise errors.oauth_token_invalid()

    payload: dict[str, Any] = response.json()
    email = payload.get("email")
    verified = payload.get("email_verified", payload.get("verified_email"))
    if not email or not verified:
        raise errors.oauth_token_invalid()
    return str(email)


def _tokens_from_payload(
    payload: dict[str, Any],
    *,
    external_account_id: str,
    previous_refresh_token: str | None,
) -> OAuthTokens:
    expires_in = payload.get("expires_in")
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=int(expires_in))
        if expires_in is not None
        else None
    )
    scope_str = payload.get("scope") or ""
    scopes = tuple(scope_str.split()) if scope_str else ()

    return OAuthTokens(
        external_account_id=external_account_id,
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token") or previous_refresh_token,
        expires_at=expires_at,
        scopes=scopes,
    )
