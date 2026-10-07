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

Two families of calls live here. ``health``/``run`` return the envelope body
and treat every non-envelope answer as a failure — that is what a read needs.
The interactive-login calls (``test_connection``/``connect_browser``/
``session``) return a :class:`ConnectResponse` instead: Connect answers 409,
422 and 404 with a typed envelope that IS the information ("another login is
in progress", "log in first", "session unknown"), so turning them into
exceptions here would force the caller to parse exception text. Transport
failures, 401/403 and 503 stay exceptions in both families.
"""

import dataclasses
import logging
from typing import Any

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.solercia_connect.errors import (
    SolerciaConnectAuthError,
    SolerciaConnectConfigError,
    SolerciaConnectNotConfiguredError,
    SolerciaConnectProtocolError,
    SolerciaConnectUnavailableError,
)

logger = logging.getLogger("solercia.connect.client")

# The envelope version this adapter was written against. Connect stamps it on
# every response; a different major means the contract moved and guessing at
# the difference would be worse than refusing.
_SUPPORTED_ENVELOPE = "solercia.connect/v1"
_API_KEY_HEADER = "X-Solercia-Connect-Key"


@dataclasses.dataclass(frozen=True)
class ConnectResponse:
    """One answer from an interactive-login call: HTTP status plus envelope.

    ``body`` is the parsed JSON object; on a 2xx it is always a
    ``solercia.connect/v1`` envelope. On a 4xx it is the envelope Connect sent
    when it sent one, or the framework's own error document (e.g. a
    validation ``{"detail": [...]}``) when it did not — the caller maps by
    ``status_code`` first and by ``error.code`` second.
    """

    status_code: int
    body: dict[str, Any]

    @property
    def ok(self) -> bool:
        return bool(self.body.get("ok"))

    @property
    def status(self) -> str | None:
        value = self.body.get("status")
        return value if isinstance(value, str) else None

    @property
    def error_code(self) -> str | None:
        error = self.body.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        return code if isinstance(code, str) else None

    @property
    def error_message(self) -> str | None:
        error = self.body.get("error")
        message = error.get("message") if isinstance(error, dict) else None
        return message if isinstance(message, str) and message.strip() else None

    @property
    def remediation(self) -> list[str]:
        """Connect's remediation hints, wherever it placed them, as text."""
        error = self.body.get("error")
        data = self.body.get("data")
        for container in (error, data, self.body):
            if not isinstance(container, dict):
                continue
            hints = container.get("remediation")
            if isinstance(hints, str) and hints.strip():
                return [hints]
            if isinstance(hints, list):
                return [hint for hint in hints if isinstance(hint, str) and hint.strip()]
        return []

    @property
    def data(self) -> dict[str, Any]:
        data = self.body.get("data")
        return data if isinstance(data, dict) else {}


class SolerciaConnectClient:
    """Client for one Connect runtime."""

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
        # Every allowlisted address is an alias of the same local runtime, so
        # a URL stored at registration time (e.g. host.docker.internal while
        # Command ran in Docker) follows the address this deployment is
        # configured with — as long as that address is itself allowlisted.
        deployed = active.SOLERCIA_CONNECT_BASE_URL.strip().rstrip("/")
        if deployed in allowlist:
            cleaned = deployed
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

    async def test_connection(
        self, *, type_: str, account: str, allow_browser_fallback: bool
    ) -> ConnectResponse:
        """``POST /v1/connections/test`` — is the stored session for ``account`` usable?"""
        return await self._envelope(
            "POST",
            "/v1/connections/test",
            json={
                "type": type_,
                "account": account,
                "allow_browser_fallback": allow_browser_fallback,
            },
        )

    async def connect_browser(self, *, type_: str, account: str) -> ConnectResponse:
        """``POST /v1/connections/connect`` — start the supervised browser login.

        ``allow_browser_fallback`` is always ``True`` here: over HTTP there is
        no terminal to show a device code on, so the browser route is the
        only one this call can start (Connect rejects ``False`` with 422).
        """
        return await self._envelope(
            "POST",
            "/v1/connections/connect",
            json={"type": type_, "account": account, "allow_browser_fallback": True},
        )

    async def session(self, session_id: str) -> ConnectResponse:
        """``GET /v1/connections/sessions/{id}`` — poll one interactive login."""
        return await self._envelope("GET", f"/v1/connections/sessions/{session_id}", json=None)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None,
        authenticated: bool,
    ) -> dict[str, Any]:
        _, body = await self._exchange(method, path, json=json, authenticated=authenticated)
        self._require_schema(body)
        return body

    async def _envelope(
        self, method: str, path: str, *, json: dict[str, Any] | None
    ) -> ConnectResponse:
        status_code, body = await self._exchange(method, path, json=json, authenticated=True)
        # A success MUST be an envelope. A 4xx is one when Connect produced it
        # and a plain framework document when its request validation did —
        # only an envelope claiming a version this adapter does not speak is
        # refused, so the caller never maps a foreign contract by accident.
        if 200 <= status_code < 300 or "schema" in body:
            self._require_schema(body)
        return ConnectResponse(status_code=status_code, body=body)

    async def _exchange(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None,
        authenticated: bool,
    ) -> tuple[int, dict[str, Any]]:
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
            raise SolerciaConnectNotConfiguredError(
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
        return response.status_code, body

    @staticmethod
    def _require_schema(body: dict[str, Any]) -> None:
        schema = body.get("schema")
        if schema != _SUPPORTED_ENVELOPE:
            raise SolerciaConnectProtocolError(
                f"Solercia Connect envelope is {schema!r}, expected {_SUPPORTED_ENVELOPE!r}"
            )
