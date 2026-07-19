"""``OidcClient`` — Authorization Code + PKCE against a generic OIDC
provider (design.md D2, sso-oidc R1/R2).

Deliberately hand-rolled on top of ``httpx`` + ``pyjwt`` instead of
``authlib`` (design.md D2 "Rejected Alternatives"): the dependency surface
stays small, matching ``app/shared/security.py``'s own ethos, and the
Authorization Code + PKCE flow is simple enough that a dedicated library
would hide more than it saves.
"""

import base64
import hashlib
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWK

from app.modules.auth.oidc.config import OidcProviderConfig
from app.modules.auth.oidc.jwks import JwksCache

_SCOPE = "openid email profile"


class OidcTokenError(Exception):
    """Raised when an ID token fails ANY validation step (design.md
    Threat Matrix — "ID token forjado"): malformed, unknown signing key,
    bad signature, wrong ``iss``/``aud``, expired, or mismatched
    ``nonce``. The caller MUST treat every case identically — reject
    without emitting a JWT — so this is intentionally a single exception
    type, not one per failure mode."""


class OidcClient:
    """One client instance per provider (holds that provider's
    :class:`OidcProviderConfig`); the shared ``httpx.AsyncClient`` and
    :class:`JwksCache` may be reused across providers."""

    def __init__(
        self,
        config: OidcProviderConfig,
        http_client: httpx.AsyncClient,
        jwks_cache: JwksCache | None = None,
    ) -> None:
        self._config = config
        self._http = http_client
        self._jwks_cache = jwks_cache or JwksCache(http_client)

    @staticmethod
    def code_challenge_s256(code_verifier: str) -> str:
        """Derive the PKCE ``code_challenge`` (RFC 7636 §4.2, S256):
        base64url(SHA256(code_verifier)), no padding."""

        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    async def authorization_url(self, state: str, nonce: str, code_challenge: str) -> str:
        """Build the provider's authorization URL for this flow's
        ``state``/``nonce``/PKCE challenge (sso-oidc R1)."""

        document = await self._jwks_cache.discovery_document(self._config.issuer)
        params = {
            "response_type": "code",
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "scope": _SCOPE,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{document['authorization_endpoint']}?{urlencode(params)}"

    async def exchange_code(self, code: str, code_verifier: str) -> dict[str, Any]:
        """Exchange the authorization ``code`` (+ PKCE ``code_verifier``)
        for tokens at the provider's ``token_endpoint``."""

        document = await self._jwks_cache.discovery_document(self._config.issuer)
        response = await self._http.post(
            document["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._config.redirect_uri,
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "code_verifier": code_verifier,
            },
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    async def verify_id_token(self, id_token: str, nonce: str) -> dict[str, Any]:
        """Validate ``id_token``'s signature (JWKS RS256), ``iss``, ``aud``,
        ``exp`` and ``nonce`` (sso-oidc R2). Raises :class:`OidcTokenError`
        on ANY failure; never returns a partially-trusted claim set."""

        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.InvalidTokenError as exc:
            raise OidcTokenError("ID token malformado.") from exc

        kid = header.get("kid")
        if not kid:
            raise OidcTokenError("ID token sin encabezado 'kid'.")

        jwk_data = await self._jwks_cache.jwks_for_kid(self._config.issuer, kid)
        if jwk_data is None:
            raise OidcTokenError(
                "La llave de firma del ID token no está publicada por el proveedor."
            )

        try:
            signing_key = PyJWK(jwk_data, algorithm="RS256").key
            claims: dict[str, Any] = jwt.decode(
                id_token,
                key=signing_key,
                algorithms=["RS256"],
                audience=self._config.client_id,
                issuer=self._config.issuer,
            )
        except jwt.InvalidTokenError as exc:
            raise OidcTokenError(f"ID token inválido: {exc}") from exc

        if claims.get("nonce") != nonce:
            raise OidcTokenError("El 'nonce' del ID token no coincide.")

        return claims
