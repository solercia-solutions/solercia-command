"""Per-issuer discovery document + JWKS cache (design.md D2).

Both are cached with a TTL so every login does not round-trip the IdP's
``.well-known`` and JWKS endpoints. The JWKS lookup ALSO refetches whenever
the requested ``kid`` is not in the cached keyset — even before the TTL
elapses — so a key rotation on the IdP side never leaves the client stuck
validating against a stale, now-retired key.
"""

import time
from dataclasses import dataclass
from typing import Any

import httpx

_DISCOVERY_TTL_SECONDS = 3600
_JWKS_TTL_SECONDS = 3600


@dataclass
class _CacheEntry:
    value: dict[str, Any]
    fetched_at: float


def _find_key(keyset: dict[str, Any], kid: str) -> dict[str, Any] | None:
    for key in keyset.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


class JwksCache:
    """Caches one issuer's discovery document and JWKS keyset in memory."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client
        self._discovery: dict[str, _CacheEntry] = {}
        self._jwks: dict[str, _CacheEntry] = {}

    async def discovery_document(self, issuer: str) -> dict[str, Any]:
        """Return the issuer's ``.well-known/openid-configuration`` body,
        cached with a TTL."""

        cached = self._discovery.get(issuer)
        if cached and (time.monotonic() - cached.fetched_at) < _DISCOVERY_TTL_SECONDS:
            return cached.value

        url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
        response = await self._http.get(url)
        response.raise_for_status()
        document: dict[str, Any] = response.json()
        self._discovery[issuer] = _CacheEntry(value=document, fetched_at=time.monotonic())
        return document

    async def jwks_for_kid(self, issuer: str, kid: str) -> dict[str, Any] | None:
        """Return the JWK matching ``kid``, or ``None`` if the IdP never
        published it. Refetches on a cache miss, an expired TTL, OR an
        unknown ``kid`` in an otherwise-fresh cache (key rotation)."""

        cached = self._jwks.get(issuer)
        if cached and (time.monotonic() - cached.fetched_at) < _JWKS_TTL_SECONDS:
            key = _find_key(cached.value, kid)
            if key is not None:
                return key

        document = await self.discovery_document(issuer)
        response = await self._http.get(document["jwks_uri"])
        response.raise_for_status()
        keyset: dict[str, Any] = response.json()
        self._jwks[issuer] = _CacheEntry(value=keyset, fetched_at=time.monotonic())
        return _find_key(keyset, kid)
