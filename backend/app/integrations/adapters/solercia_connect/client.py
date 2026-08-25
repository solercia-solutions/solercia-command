"""HTTP boundary to a local Solercia Connect runtime.

Connect is a separate product with its own deployment, so this adapter speaks
to it over its published loopback contract rather than importing it. The
platform decision record forbids the alternative outright
(``docs/decisions/2026-08-23-solercia-platform-decisions.md`` §2.2: "Se
prohíben ... las importaciones directas del repositorio hermano y las
dependencias obligatorias de arranque"), and §2.1 requires each product to
start and deliver its core behaviour with the other absent.

The runtime binds to loopback and holds a live provider session — a browser
profile or OAuth tokens belonging to one person. Reaching it from the wrong
host would mean reading somebody's mailbox, so ``SOLERCIA_CONNECT_BASE_URL_ALLOWLIST``
gates every call before it is made, the same anti-SSRF posture GLPI's
``base_url`` already uses.
"""

import logging
from typing import Any

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.solercia_connect.errors import (
    SolerciaConnectAuthError,
    SolerciaConnectConfigError,
    SolerciaConnectProtocolError,
    SolerciaConnectUnavailableError,
)

logger = logging.getLogger("solercia.connect.client")

# The envelope version this adapter was written against. Connect stamps it on
# every response; a different major means the contract moved and guessing at
# the difference would be worse than refusing.
_SUPPORTED_ENVELOPE = "solercia.connect/v1"
_API_KEY_HEADER = "X-Solercia-Connect-Key"


class SolerciaConnectClient:
    """Read-only client for one Connect runtime."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        active = settings or default_settings
        cleaned = base_url.strip().rstrip("/")
        if not cleaned:
            raise SolerciaConnectConfigError("Solercia Connect base URL is empty")
        allowlist = [
            entry.strip().rstrip("/") for entry in active.SOLERCIA_CONNECT_BASE_URL_ALLOWLIST
        ]
        if cleaned not in allowlist:
            # Naming the value would echo an operator-supplied host into logs;
            # the allowlist is the actionable half of this message.
            raise SolerciaConnectConfigError(
                "Solercia Connect base URL is not in SOLERCIA_CONNECT_BASE_URL_ALLOWLIST"
            )
        if not api_key.strip():
            raise SolerciaConnectConfigError("Solercia Connect API key is empty")
        self._base_url = cleaned
        self._api_key = api_key
        self._timeout = active.SOLERCIA_CONNECT_TIMEOUT_SECONDS
        self._transport = transport

    async def health(self) -> dict[str, Any]:
        """Read the runtime's unauthenticated health document."""
        return await self._request("GET", "/v1/health", json=None, authenticated=False)

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute one typed capability and return its envelope."""
        return await self._request("POST", "/v1/run", json=payload, authenticated=True)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None,
        authenticated: bool,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if authenticated:
            headers[_API_KEY_HEADER] = self._api_key
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.request(method, path, json=json, headers=headers)
        except httpx.HTTPError as failure:
            # A refused connection is the ordinary state of a runtime the user
            # has not started, so it is reported as unavailable rather than as
            # an error in Command.
            raise SolerciaConnectUnavailableError(
                "Solercia Connect runtime did not answer on its configured address"
            ) from failure

        if response.status_code in {401, 403}:
            raise SolerciaConnectAuthError("Solercia Connect rejected the configured API key")
        if response.status_code == 503:
            raise SolerciaConnectUnavailableError(
                "Solercia Connect is running but not configured to serve this request"
            )

        try:
            body = response.json()
        except ValueError as failure:
            raise SolerciaConnectProtocolError(
                "Solercia Connect returned a body that is not JSON"
            ) from failure
        if not isinstance(body, dict):
            raise SolerciaConnectProtocolError("Solercia Connect returned an unexpected body")

        schema = body.get("schema")
        if schema != _SUPPORTED_ENVELOPE:
            raise SolerciaConnectProtocolError(
                f"Solercia Connect envelope is {schema!r}, expected {_SUPPORTED_ENVELOPE!r}"
            )
        return body
