"""Shared fake IdP helpers for the OIDC/SSO test suites (change
20-sso-keycloak).

An RSA keypair signs ID tokens; ``FakeIdp.handler`` stands in for a real
Keycloak-shaped OIDC provider (discovery document, JWKS, token endpoint)
behind ``httpx.MockTransport`` — no real network call, no real IdP.
Shared by ``test_oidc_client.py`` (client-level R2 validations) and
``test_auth_sso.py`` (router-level R1/R2/R5/R6 flows) so the two suites
do not maintain near-identical copies of the same fixture.
"""

import base64
import time

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

DEFAULT_ISSUER = "https://idp.test/realms/demo"
DEFAULT_CLIENT_ID = "solercia-client"


def rsa_jwk(kid: str) -> tuple[bytes, dict]:
    """Generate an RSA keypair and return ``(private_pem, public_jwk)``."""

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()

    def _b64url_uint(n: int) -> str:
        raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    jwk = {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem, jwk


def sign_id_token(
    private_pem: bytes,
    kid: str,
    *,
    issuer: str = DEFAULT_ISSUER,
    audience: str = DEFAULT_CLIENT_ID,
    subject: str = "user-123",
    nonce: str = "test-nonce",
    email: str = "person@example.com",
    email_verified: bool = True,
    expires_in: int = 300,
) -> str:
    now = int(time.time())
    payload = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "exp": now + expires_in,
        "iat": now,
        "nonce": nonce,
        "email": email,
        "email_verified": email_verified,
    }
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": kid})


class FakeIdp:
    """Stubs discovery/JWKS/token endpoints; counts JWKS fetches for the
    cache-refetch assertions and lets tests set the token endpoint's next
    ID token via either ``token_response`` or the ``next_id_token``
    convenience property (both write the same underlying dict)."""

    def __init__(self, *, issuer: str = DEFAULT_ISSUER) -> None:
        self.issuer = issuer
        self.jwks_fetch_count = 0
        self._keys: dict[str, dict] = {}
        self.token_response: dict = {"access_token": "irrelevant", "id_token": ""}

    def add_key(self, kid: str, jwk: dict) -> None:
        self._keys[kid] = jwk

    @property
    def next_id_token(self) -> str:
        return self.token_response.get("id_token", "")

    @next_id_token.setter
    def next_id_token(self, value: str) -> None:
        self.token_response["id_token"] = value

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": self.issuer,
                    "authorization_endpoint": f"{self.issuer}/protocol/openid-connect/auth",
                    "token_endpoint": f"{self.issuer}/protocol/openid-connect/token",
                    "jwks_uri": f"{self.issuer}/protocol/openid-connect/certs",
                },
            )
        if request.url.path.endswith("/protocol/openid-connect/certs"):
            self.jwks_fetch_count += 1
            return httpx.Response(200, json={"keys": list(self._keys.values())})
        if request.url.path.endswith("/protocol/openid-connect/token"):
            return httpx.Response(200, json=self.token_response)
        return httpx.Response(404, json={"error": "not_found"})
