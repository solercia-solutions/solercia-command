"""Tests for the SSO login/callback routes (change 20-sso-keycloak, T15).

A fake IdP (RSA test key pair + ``httpx.MockTransport``) stands in for
Keycloak — same technique as ``test_oidc_client.py``, wired through
``app.modules.auth.oidc.client.get_http_client`` (module-qualified
monkeypatch, same idiom as ``patched_redis``). Covers R1 (login redirects
+ persists state), R2 (state invalid/reused, forged ID token), R5 (IdP
error), R6 (SSO_ENABLED=false → inert), R7 (callback never puts the
access token in the URL) plus the fixed-``redirect_uri`` posture from
design.md D5.
"""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from httpx import AsyncClient

from app.modules.auth.oidc import client as oidc_client_module
from tests.conftest import skip_no_db
from tests.fake_idp import FakeIdp as _FakeIdp
from tests.fake_idp import rsa_jwk as _rsa_jwk
from tests.fake_idp import sign_id_token as _shared_sign_id_token

_ISSUER = "https://idp.test/realms/demo"
_CLIENT_ID = "solercia-client"
_REDIRECT_URI = "http://localhost:8000/api/v1/auth/sso/keycloak/callback"
_POST_LOGIN_REDIRECT = "http://localhost:4200/auth/callback"


def _sign_id_token(
    private_pem: bytes,
    kid: str,
    *,
    nonce: str,
    email: str = "sso-person@example.com",
    email_verified: bool = True,
    expires_in: int = 300,
) -> str:
    """Router-suite defaults (fixed ``sub``, own default ``email``) on top
    of the shared ``fake_idp.sign_id_token``."""

    return _shared_sign_id_token(
        private_pem,
        kid,
        subject="idp-sub-1",
        nonce=nonce,
        email=email,
        email_verified=email_verified,
        expires_in=expires_in,
    )


@pytest.fixture
def sso_env(monkeypatch):
    """Enables SSO, configures the 'keycloak' provider and wires the fake
    IdP into ``get_http_client()`` (module-qualified monkeypatch)."""

    from app.config import settings

    monkeypatch.setattr(settings, "SSO_ENABLED", True)
    monkeypatch.setattr(settings, "SSO_POST_LOGIN_REDIRECT", _POST_LOGIN_REDIRECT)
    monkeypatch.setenv("OIDC_KEYCLOAK_ISSUER", _ISSUER)
    monkeypatch.setenv("OIDC_KEYCLOAK_CLIENT_ID", _CLIENT_ID)
    monkeypatch.setenv("OIDC_KEYCLOAK_CLIENT_SECRET", "shh")
    monkeypatch.setenv("OIDC_KEYCLOAK_REDIRECT_URI", _REDIRECT_URI)

    fake_idp = _FakeIdp()
    private_pem, jwk = _rsa_jwk("kid-1")
    fake_idp.add_key("kid-1", jwk)

    fake_http_client = httpx.AsyncClient(transport=httpx.MockTransport(fake_idp.handler))
    monkeypatch.setattr(oidc_client_module, "get_http_client", lambda: fake_http_client)

    return fake_idp, private_pem


def _state_from_location(location: str) -> str:
    query = parse_qs(urlparse(location).query)
    return query["state"][0]


# ---------------------------------------------------------------------------
# R1 — Inicio del flujo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sso_login_redirects_and_persists_state(
    client: AsyncClient, sso_env, patched_redis
) -> None:
    before = await patched_redis.dbsize()

    response = await client.get("/auth/sso/keycloak/login")

    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.startswith(f"{_ISSUER}/protocol/openid-connect/auth?")
    assert "code_challenge_method=S256" in location
    after = await patched_redis.dbsize()
    assert after == before + 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sso_login_ignores_a_client_supplied_redirect_uri(
    client: AsyncClient, sso_env, patched_redis
) -> None:
    """design.md D5 — the OIDC redirect_uri is ALWAYS the fixed,
    env-configured value ("allowlist de 1"); a caller-supplied one is
    simply not a parameter this route accepts, so it can never override
    it (sso-oidc R2, "redirect_uri pertenece a la allowlist")."""

    response = await client.get(
        "/auth/sso/keycloak/login", params={"redirect_uri": "https://attacker.test/steal"}
    )

    assert response.status_code == 302, response.text
    location = response.headers["location"]
    query = parse_qs(urlparse(location).query)
    assert query["redirect_uri"][0] == _REDIRECT_URI


# ---------------------------------------------------------------------------
# Callback feliz — R6 auth (JWT), R7 (sin access en URL)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sso_callback_happy_path_sets_refresh_cookie_without_access_in_url(
    client: AsyncClient, session, sso_env, patched_redis
) -> None:
    from app.modules.users.models import User

    session.add(
        User(
            email="sso-person@example.com",
            primer_nombre="Sso",
            primer_apellido="Person",
            hashed_password="x",
        )
    )
    await session.flush()

    fake_idp, private_pem = sso_env
    login_response = await client.get("/auth/sso/keycloak/login")
    state = _state_from_location(login_response.headers["location"])

    async def _pop_nonce() -> str:
        import json

        raw = await patched_redis.get(f"sso:state:{state}")
        return json.loads(raw)["nonce"]

    nonce = await _pop_nonce()
    fake_idp.next_id_token = _sign_id_token(private_pem, "kid-1", nonce=nonce)

    response = await client.get(
        "/auth/sso/keycloak/callback", params={"code": "auth-code-1", "state": state}
    )

    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location == _POST_LOGIN_REDIRECT
    assert "access_token" not in location
    assert "refresh_token" in response.headers.get("set-cookie", "")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sso_callback_rejects_email_link_to_an_inactive_user(
    client: AsyncClient, session, sso_env, patched_redis
) -> None:
    """The email-match link path (case (b), sso-oidc R4) must reject an
    inactive local user the SAME way case (a) rejects an inactive linked
    user — never link/emit a cookie for a soft-deleted account."""

    from sqlalchemy import select

    from app.modules.auth.models import FederatedIdentity
    from app.modules.users.models import User

    session.add(
        User(
            email="sso-person@example.com",
            primer_nombre="Sso",
            primer_apellido="Person",
            hashed_password="x",
            is_active=False,
        )
    )
    await session.flush()

    fake_idp, private_pem = sso_env
    login_response = await client.get("/auth/sso/keycloak/login")
    state = _state_from_location(login_response.headers["location"])

    import json

    raw = await patched_redis.get(f"sso:state:{state}")
    nonce = json.loads(raw)["nonce"]
    fake_idp.next_id_token = _sign_id_token(private_pem, "kid-1", nonce=nonce)

    response = await client.get(
        "/auth/sso/keycloak/callback", params={"code": "auth-code-1", "state": state}
    )

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "sso_login_rejected"
    assert "set-cookie" not in response.headers

    identities = await session.execute(select(FederatedIdentity))
    assert identities.scalars().all() == []


# ---------------------------------------------------------------------------
# R2 — state inválido/reusado, ID token forjado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sso_callback_rejects_unknown_state(
    client: AsyncClient, sso_env, patched_redis
) -> None:
    response = await client.get(
        "/auth/sso/keycloak/callback",
        params={"code": "some-code", "state": "never-issued-state"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "sso_state_invalid"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sso_callback_rejects_a_reused_state(
    client: AsyncClient, session, sso_env, patched_redis
) -> None:
    from app.modules.users.models import User

    session.add(
        User(
            email="sso-person@example.com",
            primer_nombre="Sso",
            primer_apellido="Person",
            hashed_password="x",
        )
    )
    await session.flush()

    fake_idp, private_pem = sso_env
    login_response = await client.get("/auth/sso/keycloak/login")
    state = _state_from_location(login_response.headers["location"])

    import json

    raw = await patched_redis.get(f"sso:state:{state}")
    nonce = json.loads(raw)["nonce"]
    fake_idp.next_id_token = _sign_id_token(private_pem, "kid-1", nonce=nonce)

    first = await client.get(
        "/auth/sso/keycloak/callback", params={"code": "reused-code", "state": state}
    )
    assert first.status_code == 302, first.text

    second = await client.get(
        "/auth/sso/keycloak/callback", params={"code": "reused-code", "state": state}
    )
    assert second.status_code == 400
    assert second.json()["code"] == "sso_state_invalid"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sso_callback_rejects_a_forged_id_token(
    client: AsyncClient, sso_env, patched_redis
) -> None:
    """The token is signed with a key NEVER published in the fake IdP's
    JWKS — a forged/attacker-controlled signature."""

    fake_idp, _real_private_pem = sso_env
    login_response = await client.get("/auth/sso/keycloak/login")
    state = _state_from_location(login_response.headers["location"])

    import json

    raw = await patched_redis.get(f"sso:state:{state}")
    nonce = json.loads(raw)["nonce"]

    forged_private_pem, _forged_jwk = _rsa_jwk("kid-1")  # same kid, different key
    fake_idp.next_id_token = _sign_id_token(forged_private_pem, "kid-1", nonce=nonce)

    response = await client.get(
        "/auth/sso/keycloak/callback", params={"code": "forged-code", "state": state}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "sso_id_token_invalid"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sso_callback_rejects_a_state_issued_for_a_different_provider(
    client: AsyncClient, sso_env, patched_redis, monkeypatch
) -> None:
    """A ``state`` issued for ``keycloak`` must never be honoured on a
    DIFFERENT provider's callback path, even if that other provider is
    also configured — cross-provider state/path confusion (sso-oidc R2)."""

    monkeypatch.setenv("OIDC_AZUREAD_ISSUER", "https://idp.test/realms/other")
    monkeypatch.setenv("OIDC_AZUREAD_CLIENT_ID", "other-client")
    monkeypatch.setenv("OIDC_AZUREAD_CLIENT_SECRET", "shh-other")
    monkeypatch.setenv(
        "OIDC_AZUREAD_REDIRECT_URI",
        "http://localhost:8000/api/v1/auth/sso/azuread/callback",
    )

    login_response = await client.get("/auth/sso/keycloak/login")
    state = _state_from_location(login_response.headers["location"])

    response = await client.get(
        "/auth/sso/azuread/callback", params={"code": "some-code", "state": state}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "sso_state_invalid"


# ---------------------------------------------------------------------------
# R5 — error del IdP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sso_callback_redirects_with_error_param_on_idp_error(
    client: AsyncClient, sso_env, patched_redis
) -> None:
    login_response = await client.get("/auth/sso/keycloak/login")
    state = _state_from_location(login_response.headers["location"])

    response = await client.get(
        "/auth/sso/keycloak/callback", params={"error": "access_denied", "state": state}
    )

    assert response.status_code == 302, response.text
    assert response.headers["location"] == f"{_POST_LOGIN_REDIRECT}?error=access_denied"
    assert "set-cookie" not in response.headers


# ---------------------------------------------------------------------------
# R6 sso-oidc — SSO_ENABLED=false → endpoints inertes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sso_endpoints_are_inert_when_sso_disabled(
    client: AsyncClient, monkeypatch
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "SSO_ENABLED", False)

    login_response = await client.get("/auth/sso/keycloak/login")
    callback_response = await client.get(
        "/auth/sso/keycloak/callback", params={"code": "x", "state": "y"}
    )

    assert login_response.status_code == 404
    assert login_response.json()["code"] == "sso_disabled"
    assert callback_response.status_code == 404
    assert callback_response.json()["code"] == "sso_disabled"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sso_login_is_inert_for_an_unconfigured_provider(
    client: AsyncClient, monkeypatch
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "SSO_ENABLED", True)
    for suffix in ("ISSUER", "CLIENT_ID", "CLIENT_SECRET", "REDIRECT_URI"):
        monkeypatch.delenv(f"OIDC_UNKNOWNIDP_{suffix}", raising=False)

    response = await client.get("/auth/sso/unknownidp/login")

    assert response.status_code == 404
    assert response.json()["code"] == "sso_disabled"
