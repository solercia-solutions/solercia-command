"""Reusable in-memory MCP ``transport_factory`` fixture (change
19-mcp-connector, Lote 1, MC-R11).

Wires ``ClientSession`` to the fake ``FastMCP`` server (``fake_server.py``)
purely in-memory via the SDK's own ``mcp.shared.memory.
create_connected_server_and_client_session`` — the SAME primitive the SDK's
own test suite uses to validate the wire protocol without a real socket.
Reused by Lote 4 (``test_mcp_adapter_reader.py``) and Lote 6
(``test_connectors_mcp_reader.py``) as the injected ``transport_factory`` for
``app.integrations.adapters.mcp.session.open_session`` — matching the
``TransportFactory`` contract: ``(ctx, pinned) -> AsyncContextManager[ClientSession]``
(``session.py``'s docstring, "why a factory yields an ALREADY-initialized
ClientSession").
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx

from mcp import ClientSession, McpError
from mcp import types as mcp_types
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import ErrorData
from tests.fixtures.mcp.fake_server import build_fake_mcp_app

TransportFactory = Callable[[Any, Any], "AsyncIterator[ClientSession]"]


def make_fake_transport_factory() -> TransportFactory:
    """Return a `transport_factory(ctx, pinned)` bound to a FRESH fake server
    instance — never shared mutable state across tests."""

    app = build_fake_mcp_app()

    @asynccontextmanager
    async def _factory(ctx: object, pinned: object) -> AsyncIterator[ClientSession]:
        # `_mcp_server` is FastMCP's only handle to the low-level `Server`
        # `create_connected_server_and_client_session` expects — there is no
        # public accessor (same reach-in the SDK's own tests use).
        async with create_connected_server_and_client_session(
            app._mcp_server  # noqa: SLF001 - no public accessor, see docstring
        ) as session:
            yield session

    return _factory


@asynccontextmanager
async def unreachable_transport_factory(
    ctx: object, pinned: object
) -> AsyncIterator[ClientSession]:
    """A `transport_factory` that simulates a server that never answers the
    connection attempt — maps to ``McpServerUnreachableError`` in
    ``session.open_session`` (MC-R3, "servidor inalcanzable en initialize")."""

    raise ConnectionError("Fake MCP server inalcanzable (simulado).")
    yield  # pragma: no cover - unreachable, required for async-generator shape


@asynccontextmanager
async def timeout_transport_factory(ctx: object, pinned: object) -> AsyncIterator[ClientSession]:
    """A `transport_factory` that simulates a connection attempt that never
    completes in time — maps to ``McpTimeoutError`` in
    ``session.open_session`` (MC-R6, "timeout por llamada")."""

    raise TimeoutError("Fake MCP server no respondió a tiempo (simulado).")
    yield  # pragma: no cover - unreachable, required for async-generator shape


@asynccontextmanager
async def mcp_error_timeout_transport_factory(
    ctx: object, pinned: object
) -> AsyncIterator[ClientSession]:
    """Raises `mcp.McpError` with `code=REQUEST_TIMEOUT` — maps to
    ``McpTimeoutError`` in ``session.open_session`` (Fix 5 coverage)."""

    raise McpError(
        ErrorData(code=httpx.codes.REQUEST_TIMEOUT, message="Fake MCP timeout (simulado).")
    )
    yield  # pragma: no cover - unreachable, required for async-generator shape


@asynccontextmanager
async def mcp_error_generic_transport_factory(
    ctx: object, pinned: object
) -> AsyncIterator[ClientSession]:
    """Raises a GENERIC `mcp.McpError` (not a timeout code) — maps to
    ``McpOperationError`` in ``session.open_session`` (Fix 5 coverage)."""

    raise McpError(ErrorData(code=-32000, message="Fake MCP protocol error (simulado)."))
    yield  # pragma: no cover - unreachable, required for async-generator shape


@asynccontextmanager
async def malformed_response_transport_factory(
    ctx: object, pinned: object
) -> AsyncIterator[Any]:
    """Yielded session raises a REAL `pydantic.ValidationError` from
    `list_resources()` — an out-of-spec response the SDK's own atomic
    validation rejects (Fix 3; maps to `McpProtocolError`)."""

    class _MalformedSession:
        async def list_resources(self) -> mcp_types.Resource:
            # Missing required fields (`uri`, `name`) -> a REAL
            # `pydantic.ValidationError`.
            return mcp_types.Resource.model_validate({})

    yield _MalformedSession()
