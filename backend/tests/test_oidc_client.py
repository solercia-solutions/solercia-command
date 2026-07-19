"""Tests for ``OidcClient`` (change 20-sso-keycloak, T09/T10).

Uses a fake IdP: an RSA test key pair signs ID tokens, and
``httpx.MockTransport`` stubs the provider's discovery document, JWKS
endpoint and token endpoint — no real network call, no real Redis/DB.
Covers R2 (sso-oidc): signature, ``iss``/``aud``/``exp``/``nonce``
validation, PKCE S256 correctness (RFC 7636 test vector) and JWKS
caching + refetch on an unknown ``kid`` (key rotation).
"""

import time

import httpx
import jwt
import pytest

from app.modules.auth.oidc.client import OidcClient, OidcTokenError
from app.modules.auth.oidc.config import OidcProviderConfig
from app.modules.auth.oidc.jwks import JwksCache
from tests.fake_idp import FakeIdp as _FakeIdp
from tests.fake_idp import rsa_jwk as _rsa_jwk
from tests.fake_idp import sign_id_token as _sign_id_token

_ISSUER = "https://idp.test/realms/demo"
_CLIENT_ID = "solercia-client"


def _client_for(fake_idp: _FakeIdp) -> OidcClient:
    transport = httpx.MockTransport(fake_idp.handler)
    http_client = httpx.AsyncClient(transport=transport)
    config = OidcProviderConfig(
        provider="keycloak",
        issuer=_ISSUER,
        client_id=_CLIENT_ID,
        client_secret="shh",
        redirect_uri="http://localhost:4200/auth/callback",
    )
    return OidcClient(config, http_client, jwks_cache=JwksCache(http_client))


# ---------------------------------------------------------------------------
# PKCE S256 — RFC 7636 Appendix B test vector
# ---------------------------------------------------------------------------


def test_code_challenge_s256_matches_rfc7636_test_vector() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    expected_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

    assert OidcClient.code_challenge_s256(verifier) == expected_challenge


def test_code_challenge_s256_differs_for_a_different_verifier() -> None:
    """Triangulation: a different verifier produces a different challenge —
    proves the hash is real, not a hardcoded passthrough."""

    other = OidcClient.code_challenge_s256("a-completely-different-verifier-value")

    assert other != "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert len(other) > 0


# ---------------------------------------------------------------------------
# authorization_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authorization_url_includes_state_nonce_and_challenge() -> None:
    fake_idp = _FakeIdp()
    client = _client_for(fake_idp)

    url = await client.authorization_url(
        state="state-abc", nonce="nonce-xyz", code_challenge="challenge-123"
    )

    assert url.startswith(f"{_ISSUER}/protocol/openid-connect/auth?")
    assert "state=state-abc" in url
    assert "nonce=nonce-xyz" in url
    assert "code_challenge=challenge-123" in url
    assert "code_challenge_method=S256" in url
    assert f"client_id={_CLIENT_ID}" in url


# ---------------------------------------------------------------------------
# exchange_code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exchange_code_returns_the_token_endpoint_response() -> None:
    fake_idp = _FakeIdp()
    fake_idp.token_response = {"access_token": "at-1", "id_token": "id-1"}
    client = _client_for(fake_idp)

    tokens = await client.exchange_code("auth-code", "verifier-value")

    assert tokens == {"access_token": "at-1", "id_token": "id-1"}


# ---------------------------------------------------------------------------
# verify_id_token — happy path + R2 validations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_id_token_accepts_a_validly_signed_token() -> None:
    fake_idp = _FakeIdp()
    private_pem, jwk = _rsa_jwk("kid-1")
    fake_idp.add_key("kid-1", jwk)
    client = _client_for(fake_idp)
    token = _sign_id_token(private_pem, "kid-1", nonce="matching-nonce")

    claims = await client.verify_id_token(token, nonce="matching-nonce")

    assert claims["sub"] == "user-123"
    assert claims["email_verified"] is True


@pytest.mark.asyncio
async def test_verify_id_token_rejects_wrong_issuer() -> None:
    fake_idp = _FakeIdp()
    private_pem, jwk = _rsa_jwk("kid-1")
    fake_idp.add_key("kid-1", jwk)
    client = _client_for(fake_idp)
    token = _sign_id_token(private_pem, "kid-1", issuer="https://attacker.test/evil")

    with pytest.raises(OidcTokenError):
        await client.verify_id_token(token, nonce="test-nonce")


@pytest.mark.asyncio
async def test_verify_id_token_rejects_wrong_audience() -> None:
    fake_idp = _FakeIdp()
    private_pem, jwk = _rsa_jwk("kid-1")
    fake_idp.add_key("kid-1", jwk)
    client = _client_for(fake_idp)
    token = _sign_id_token(private_pem, "kid-1", audience="some-other-client")

    with pytest.raises(OidcTokenError):
        await client.verify_id_token(token, nonce="test-nonce")


@pytest.mark.asyncio
async def test_verify_id_token_rejects_an_expired_token() -> None:
    fake_idp = _FakeIdp()
    private_pem, jwk = _rsa_jwk("kid-1")
    fake_idp.add_key("kid-1", jwk)
    client = _client_for(fake_idp)
    token = _sign_id_token(private_pem, "kid-1", expires_in=-60)

    with pytest.raises(OidcTokenError):
        await client.verify_id_token(token, nonce="test-nonce")


@pytest.mark.asyncio
async def test_verify_id_token_rejects_a_token_missing_the_exp_claim() -> None:
    """PyJWT only validates ``exp``/``iat`` when they are PRESENT; a token
    that omits ``exp`` entirely would otherwise sail through as
    non-expiring. ``options={"require": [...]}`` closes that gap."""

    fake_idp = _FakeIdp()
    private_pem, jwk = _rsa_jwk("kid-1")
    fake_idp.add_key("kid-1", jwk)
    client = _client_for(fake_idp)

    now = int(time.time())
    payload = {
        "iss": _ISSUER,
        "aud": _CLIENT_ID,
        "sub": "user-123",
        # "exp" intentionally omitted.
        "iat": now,
        "nonce": "test-nonce",
        "email": "person@example.com",
        "email_verified": True,
    }
    token = jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": "kid-1"})

    with pytest.raises(OidcTokenError):
        await client.verify_id_token(token, nonce="test-nonce")


@pytest.mark.asyncio
async def test_verify_id_token_rejects_mismatched_nonce() -> None:
    fake_idp = _FakeIdp()
    private_pem, jwk = _rsa_jwk("kid-1")
    fake_idp.add_key("kid-1", jwk)
    client = _client_for(fake_idp)
    token = _sign_id_token(private_pem, "kid-1", nonce="expected-nonce")

    with pytest.raises(OidcTokenError):
        await client.verify_id_token(token, nonce="a-different-nonce")


@pytest.mark.asyncio
async def test_verify_id_token_rejects_a_token_signed_by_an_unknown_key() -> None:
    """A token signed by a key NEVER published in the IdP's JWKS (forged /
    attacker-controlled key) must be rejected."""

    fake_idp = _FakeIdp()
    # The IdP's real JWKS only ever exposes "kid-1"...
    _real_private_pem, real_jwk = _rsa_jwk("kid-1")
    fake_idp.add_key("kid-1", real_jwk)
    client = _client_for(fake_idp)

    # ...but the token is signed with a DIFFERENT, never-published key,
    # forging the SAME kid to try to slip past a naive kid-only check.
    forged_private_pem, _forged_jwk = _rsa_jwk("kid-1")
    token = _sign_id_token(forged_private_pem, "kid-1")

    with pytest.raises(OidcTokenError):
        await client.verify_id_token(token, nonce="test-nonce")


# ---------------------------------------------------------------------------
# JWKS cache + refetch on unknown kid (key rotation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jwks_is_cached_and_not_refetched_for_a_known_kid() -> None:
    fake_idp = _FakeIdp()
    private_pem, jwk = _rsa_jwk("kid-1")
    fake_idp.add_key("kid-1", jwk)
    client = _client_for(fake_idp)
    token = _sign_id_token(private_pem, "kid-1")

    await client.verify_id_token(token, nonce="test-nonce")
    await client.verify_id_token(token, nonce="test-nonce")

    assert fake_idp.jwks_fetch_count == 1


@pytest.mark.asyncio
async def test_jwks_refetches_when_an_unknown_kid_appears() -> None:
    """Simulates key rotation: the IdP starts signing with a NEW kid that
    was not in the cached JWKS — the client must refetch and succeed."""

    fake_idp = _FakeIdp()
    old_private_pem, old_jwk = _rsa_jwk("kid-old")
    fake_idp.add_key("kid-old", old_jwk)
    client = _client_for(fake_idp)

    old_token = _sign_id_token(old_private_pem, "kid-old")
    await client.verify_id_token(old_token, nonce="test-nonce")
    assert fake_idp.jwks_fetch_count == 1

    # IdP rotates: publishes a new key under a new kid.
    new_private_pem, new_jwk = _rsa_jwk("kid-new")
    fake_idp.add_key("kid-new", new_jwk)
    new_token = _sign_id_token(new_private_pem, "kid-new")

    claims = await client.verify_id_token(new_token, nonce="test-nonce")

    assert claims["sub"] == "user-123"
    assert fake_idp.jwks_fetch_count == 2
