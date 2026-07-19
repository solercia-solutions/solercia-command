"""Ephemeral MCP client session (change 19-mcp-connector, design.md "Ciclo
de sesión: `initialize` POR OPERACIÓN" — open, `initialize`, use, close; NO
session-level cache. Rationale in design.md Architecture Decisions: a
cached session would be shared mutable state with cross-tenant leak risk
and `Mcp-Session-Id` expiry to manage; the extra round-trip is acceptable
for low-frequency admin/member reads and bounded by
``MCP_CONNECT_TIMEOUT_SECONDS``).

``McpAccessContext`` is the MCP-specific handle every ``reader.py`` method
decodes from the core's generic ``AccessContext`` — mirrors GLPI's
``encode_access_context``/``_decode_access_context`` precedent
(``adapters/glpi/adapter.py``): the core's ``AccessContext`` is NEVER
extended with provider-specific fields, ``base_url``/``token``/
``tools_allowlist`` travel packed as an opaque JSON string inside
``AccessContext.access_token``.
"""

import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta

import httpx
from mcp import ClientSession, McpError
from mcp.client.streamable_http import streamablehttp_client

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.mcp import errors
from app.integrations.adapters.mcp.ssrf import PinnedTarget, validate_mcp_url
from app.integrations.ports import AccessContext


@dataclass(frozen=True)
class McpAccessContext:
    """The MCP-specific handle decoded from ``AccessContext.access_token``."""

    base_url: str
    token: str | None
    tools_allowlist: frozenset[str]


def encode_access_context(
    *, base_url: str, token: str | None, tools_allowlist: frozenset[str] | set[str]
) -> str:
    """Build the opaque JSON payload for ``AccessContext.access_token`` —
    the ONE place that packs MCP-specific fields without touching the
    core's ``AccessContext`` shape (mirrors GLPI's ``encode_access_context``)."""

    payload = {
        "base_url": base_url,
        "token": token,
        "tools_allowlist": sorted(tools_allowlist),
    }
    return json.dumps(payload)


def decode_access_context(ctx: AccessContext) -> McpAccessContext:
    """Inverse of :func:`encode_access_context` — raises
    :class:`errors.McpOperationError` for a malformed/incomplete payload,
    never an unhandled `json.JSONDecodeError`/`KeyError`."""

    try:
        payload: dict[str, object] = json.loads(ctx.access_token)
    except (TypeError, ValueError) as exc:
        raise errors.McpOperationError(
            "El contexto de acceso del conector MCP es inválido."
        ) from exc

    base_url = payload.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        raise errors.McpOperationError(
            "El contexto de acceso del conector MCP está incompleto."
        )
    token = payload.get("token")
    allowlist_raw = payload.get("tools_allowlist") or ()
    tools_allowlist = frozenset(allowlist_raw) if isinstance(allowlist_raw, list) else frozenset()
    return McpAccessContext(
        base_url=base_url,
        token=token if isinstance(token, str) else None,
        tools_allowlist=tools_allowlist,
    )


TransportFactory = Callable[
    [McpAccessContext, PinnedTarget], AbstractAsyncContextManager[ClientSession]
]


class _PinnedIPTransport(httpx.AsyncHTTPTransport):
    """Connects to ``pinned_ip`` while preserving the ORIGINAL hostname for
    the ``Host`` header and TLS SNI (design.md, "httpx conecta a la IP
    validada preservando Host/SNI") — the IP-pin itself: even if DNS for
    ``original_host`` changes between ``validate_mcp_url`` and this
    connection, the socket still targets the ALREADY-VETTED address."""

    def __init__(self, *, pinned_ip: str, original_host: str) -> None:
        super().__init__()
        self._pinned_ip = pinned_ip
        self._original_host = original_host

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        request.url = request.url.copy_with(host=self._pinned_ip)
        request.headers["host"] = self._original_host
        request.extensions["sni_hostname"] = self._original_host
        return await super().handle_async_request(request)


@asynccontextmanager
async def streamable_http_default(
    ctx: McpAccessContext, pinned: PinnedTarget, *, settings: Settings = default_settings
) -> AsyncIterator[ClientSession]:
    """The REAL transport factory — Streamable HTTP over the IP-pinned
    target, `initialize`d before yielding. Never exercised by the test
    suite directly (MC-R11's in-memory fake server is the harness that
    stands in for this factory); kept dependency-injectable so wiring a
    real deployment is a config change, never a code change."""

    headers = {"Authorization": f"Bearer {ctx.token}"} if ctx.token else None

    def _http_client_factory(
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
    ) -> httpx.AsyncClient:
        transport = _PinnedIPTransport(pinned_ip=pinned.ip, original_host=pinned.host)
        return httpx.AsyncClient(transport=transport, headers=headers, timeout=timeout, auth=auth)

    async with (
        streamablehttp_client(
            ctx.base_url,
            headers=headers,
            timeout=settings.MCP_CONNECT_TIMEOUT_SECONDS,
            sse_read_timeout=settings.MCP_TOTAL_TIMEOUT_SECONDS,
            httpx_client_factory=_http_client_factory,
        ) as (read_stream, write_stream, _get_session_id),
        ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timedelta(seconds=settings.MCP_TOTAL_TIMEOUT_SECONDS),
        ) as session,
    ):
        await session.initialize()
        yield session


@asynccontextmanager
async def open_session(
    ctx: McpAccessContext,
    *,
    transport_factory: TransportFactory = streamable_http_default,
    settings: Settings = default_settings,
) -> AsyncIterator[ClientSession]:
    """Open an EPHEMERAL MCP session: validate the URL (anti-SSRF, IP-pin,
    MC-R7) BEFORE opening any socket, connect+`initialize` via
    ``transport_factory`` (MC-R3), yield the ready session. Every
    network/timeout failure is translated into a controlled
    :class:`app.shared.exceptions.AppException` subclass — never an
    unhandled exception (MC-R3, MC-R6).
    """

    pinned = await validate_mcp_url(ctx.base_url, settings=settings)
    try:
        async with transport_factory(ctx, pinned) as session:
            yield session
    except TimeoutError as exc:
        raise errors.McpTimeoutError() from exc
    except httpx.TimeoutException as exc:
        raise errors.McpTimeoutError() from exc
    except McpError as exc:
        if exc.error.code == httpx.codes.REQUEST_TIMEOUT:
            raise errors.McpTimeoutError() from exc
        raise errors.McpOperationError() from exc
    except (httpx.HTTPError, OSError) as exc:
        raise errors.McpServerUnreachableError() from exc
