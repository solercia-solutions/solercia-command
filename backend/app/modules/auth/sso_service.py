"""SSO (OIDC) login/callback orchestration (design.md D3/D4, sso-oidc R1-R5).

Two responsibilities live here:

1. **Ephemeral state** (``state``/``nonce``/``code_verifier``) in Redis
   under ``sso:state:{state}``, TTL 300 s, single-use (``GETDEL``) — same
   pattern as ``app/integrations/state_store.py`` (change
   14-integration-ports), under its OWN key prefix so an OAuth connector
   state and an SSO login state never collide even on the same value.
   Calls ``shared_redis.get_redis_client()`` through the MODULE (not a
   direct ``from ... import get_redis_client``) so tests can monkeypatch
   ``app.shared.redis.get_redis_client`` — see ``tests/conftest.py``'s
   ``patched_redis`` fixture.

2. **User resolution** (:func:`resolve_or_provision_user`) — the ONLY
   place that implements sso-oidc R4's ordering: existing
   ``(issuer, subject)`` link, then email match (link), then
   auto-provision (or reject). Deliberately pure w.r.t. Redis/HTTP so it
   is unit-testable against a plain DB session.
"""

import json
import secrets
from typing import Any

import httpx
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.auth.models import FederatedIdentity
from app.modules.auth.oidc.client import OidcClient
from app.modules.auth.oidc.config import OidcProviderConfig, load_provider_config
from app.modules.users.models import User
from app.shared import redis as shared_redis
from app.shared.exceptions import AppException

_STATE_KEY_PREFIX = "sso:state:"
_STATE_TTL_SECONDS = 300

_UNAVAILABLE_MESSAGE = (
    "El servicio de inicio de sesión no está disponible en este momento. "
    "Inténtalo de nuevo en unos minutos."
)


class SsoDisabledError(Exception):
    """SSO is off, or ``provider`` has no complete env configuration
    (sso-oidc R6 — the caller MUST render this as an inert 404, never a
    500)."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"SSO is disabled or unconfigured for provider: {provider}")


class SsoStateInvalidError(Exception):
    """The callback's ``state`` is missing, expired or already consumed
    (sso-oidc R2 — single-use anti-replay)."""

    def __init__(self, state: str) -> None:
        self.state = state
        super().__init__(f"SSO state not found or expired: {state}")


class SsoLoginRejectedError(Exception):
    """The callback could not resolve/provision a local user (sso-oidc
    R3/R4): unverified email, or no match with auto-provision off."""


def _state_key(state: str) -> str:
    return f"{_STATE_KEY_PREFIX}{state}"


def _unavailable(exc: Exception) -> AppException:
    return AppException(_UNAVAILABLE_MESSAGE, code="sso_state_unavailable", status_code=503)


async def put_state(state: str, payload: dict[str, Any]) -> None:
    """Persist ``payload`` under ``state`` with the 300s TTL (sso-oidc R1)."""

    client = shared_redis.get_redis_client()
    try:
        await client.set(_state_key(state), json.dumps(payload), ex=_STATE_TTL_SECONDS)
    except RedisError as exc:
        raise _unavailable(exc) from exc


async def pop_state(state: str) -> dict[str, Any] | None:
    """Atomically read-and-delete ``state``'s payload (single-use).

    Returns ``None`` when the state does not exist — missing, expired or
    already consumed are indistinguishable by design, same as
    ``app/integrations/state_store.py``.
    """

    client = shared_redis.get_redis_client()
    try:
        raw = await client.getdel(_state_key(state))
    except RedisError as exc:
        raise _unavailable(exc) from exc
    if raw is None:
        return None
    result: dict[str, Any] = json.loads(raw)
    return result


def require_provider_config(provider: str) -> OidcProviderConfig:
    """Return ``provider``'s config, or raise :class:`SsoDisabledError`
    when SSO is off or the provider is not (fully) configured."""

    if not settings.SSO_ENABLED:
        raise SsoDisabledError(provider)
    config = load_provider_config(provider)
    if config is None:
        raise SsoDisabledError(provider)
    return config


async def resolve_or_provision_user(
    db: AsyncSession, provider: str, claims: dict[str, Any]
) -> User:
    """Resolve the local ``User`` for a validated ID token's claims,
    following sso-oidc R4's order exactly:

    (a) an existing :class:`FederatedIdentity` for ``(issuer, subject)`` —
        reuse it, never duplicate (idempotent re-login).
    (b) no existing link, ``email_verified=True`` and a local user with
        that email exists — link it (creates the identity row).
    (c) no match and ``SSO_AUTO_PROVISION=False`` (default) — reject,
        create nothing.
    (d) no match and ``SSO_AUTO_PROVISION=True`` — create the local user
        (``hashed_password=None``, no RBAC role) and link it.

    ``email_verified=False`` rejects BEFORE any lookup/creation in cases
    (b)-(d) — case (a) never re-checks it: the account was already
    verified at link time (sso-oidc R3, "Enlace idempotente por sub").
    """

    issuer = claims["iss"]
    subject = claims["sub"]

    existing = await db.execute(
        select(FederatedIdentity).where(
            FederatedIdentity.issuer == issuer,
            FederatedIdentity.subject == subject,
            FederatedIdentity.is_active.is_(True),
        )
    )
    identity = existing.scalar_one_or_none()
    if identity is not None:
        user_result = await db.execute(select(User).where(User.id == identity.user_id))
        user = user_result.scalar_one_or_none()
        if user is not None and user.is_active:
            return user
        raise SsoLoginRejectedError("Linked user no longer exists or is inactive.")

    if not claims.get("email_verified"):
        raise SsoLoginRejectedError("email_verified is not true; cannot link or provision.")

    email = str(claims["email"]).strip().lower()

    user_result = await db.execute(select(User).where(User.email == email))
    user = user_result.scalar_one_or_none()

    if user is None:
        if not settings.SSO_AUTO_PROVISION:
            raise SsoLoginRejectedError(
                "No local user matches this email and SSO_AUTO_PROVISION is off."
            )
        name_parts = email.split("@", 1)[0]
        user = User(
            email=email,
            primer_nombre=name_parts or "SSO",
            primer_apellido=provider,
            hashed_password=None,
        )
        db.add(user)
        await db.flush()

    db.add(
        FederatedIdentity(
            user_id=user.id,
            provider=provider,
            issuer=issuer,
            subject=subject,
            email=email,
        )
    )
    await db.flush()
    return user


def build_authorization_state(code_verifier: str) -> str:
    """Derive the PKCE ``code_challenge`` for ``code_verifier`` (S256)."""

    return OidcClient.code_challenge_s256(code_verifier)


async def sso_login(provider: str, http_client: httpx.AsyncClient) -> str:
    """Start the SSO flow (sso-oidc R1): generate ``state``/``nonce``/PKCE,
    persist the state in Redis, and return the provider's authorization
    URL for the caller to redirect the browser to."""

    config = require_provider_config(provider)

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = build_authorization_state(code_verifier)

    await put_state(
        state, {"nonce": nonce, "code_verifier": code_verifier, "provider": provider}
    )

    client = OidcClient(config, http_client)
    return await client.authorization_url(state, nonce, code_challenge)


async def sso_callback(
    db: AsyncSession,
    provider: str,
    http_client: httpx.AsyncClient,
    *,
    code: str | None,
    state: str | None,
    error: str | None,
) -> tuple[str, str, User]:
    """Complete the SSO flow (sso-oidc R2-R5): validate ``state``, exchange
    the code, verify the ID token, resolve/provision the user.

    Returns ``(access_token, refresh_token, user)`` on success. The
    caller (router) is responsible for setting the refresh cookie and
    redirecting — this function never touches the HTTP response.
    """

    from app.shared.security import create_access_token, create_refresh_token

    config = require_provider_config(provider)

    if error:
        raise SsoLoginRejectedError(f"IdP returned an error: {error}")

    if not state:
        raise SsoStateInvalidError(state or "")

    payload = await pop_state(state)
    if payload is None:
        raise SsoStateInvalidError(state)

    if not code:
        raise SsoLoginRejectedError("Missing authorization code.")

    client = OidcClient(config, http_client)
    tokens = await client.exchange_code(code, payload["code_verifier"])
    id_token = tokens.get("id_token")
    if not id_token:
        raise SsoLoginRejectedError("Provider response is missing an id_token.")

    claims = await client.verify_id_token(id_token, payload["nonce"])

    user = await resolve_or_provision_user(db, provider, claims)

    access_token = create_access_token(str(user.id))
    refresh_token, _ = create_refresh_token(str(user.id))
    return access_token, refresh_token, user
