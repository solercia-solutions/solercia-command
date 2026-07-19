"""RED tests for the MCP adapter's ephemeral session + reader (change
19-mcp-connector, Lote 4, mcp-connector/spec.md MC-R3/MC-R4/MC-R5/MC-R6/MC-R8).

Exercises `McpResourceReader` against the REAL wire protocol via the fake
in-memory `FastMCP` server (`tests/fixtures/mcp`, Lote 1) with an INJECTED
`transport_factory` — zero real network, but a REAL `ClientSession`
round-trip (MC-R11). `unreachable_transport_factory`/`timeout_transport_factory`
simulate the two failure modes `open_session` must translate into domain
errors without a real, slow/broken network to reproduce them against.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from mcp import ClientSession

from app.config import Settings
from app.integrations.adapters.mcp import errors
from app.integrations.adapters.mcp.reader import McpResourceReader
from app.integrations.adapters.mcp.session import encode_access_context
from app.integrations.ports import AccessContext
from tests.fixtures.mcp import (
    make_fake_transport_factory,
    timeout_transport_factory,
    unreachable_transport_factory,
)
from tests.fixtures.mcp.fake_server import (
    LARGE_RESOURCE_BYTES,
    READ_ONLY_TOOL_ECHO_PREFIX,
    SMALL_RESOURCE_TEXT,
)

_FAKE_BASE_URL = "https://127.0.0.1:9443/mcp/fake"


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "MCP_HOST_ALLOWLIST": ["127.0.0.1"],
        "MCP_MAX_LIST_ITEMS": 100,
        "MCP_MAX_RESOURCE_BYTES": 1_048_576,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _ctx(
    *, token: str | None = None, tools_allowlist: frozenset[str] = frozenset()
) -> AccessContext:
    return AccessContext(
        access_token=encode_access_context(
            base_url=_FAKE_BASE_URL, token=token, tools_allowlist=tools_allowlist
        ),
        refresh_token=None,
        scopes=(),
    )


@asynccontextmanager
async def _never_called_transport_factory(
    ctx: object, pinned: object
) -> AsyncIterator[ClientSession]:
    raise AssertionError("El reader NO debe contactar al servidor en este escenario.")
    yield  # pragma: no cover - unreachable, required for async-generator shape


# ---------------------------------------------------------------------------
# MC-R3 — initialize previo / servidor inalcanzable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_list_resources_against_reachable_fake_server_succeeds() -> None:
    """Scenario: Initialize exitoso habilita las llamadas siguientes."""

    reader = McpResourceReader(
        settings=_settings(), transport_factory=make_fake_transport_factory()
    )

    resources = await reader.list_resources(_ctx())

    assert any(resource.uri == "fake://notes/small" for resource in resources)


@pytest.mark.asyncio(loop_scope="session")
async def test_unreachable_server_at_initialize_raises_server_unreachable_error() -> None:
    """Scenario: Servidor inalcanzable en `initialize`."""

    reader = McpResourceReader(
        settings=_settings(), transport_factory=unreachable_transport_factory
    )

    with pytest.raises(errors.McpServerUnreachableError):
        await reader.list_resources(_ctx())


# ---------------------------------------------------------------------------
# MC-R4 — recursos con tope de tamaño
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_list_resources_maps_to_external_resource_dtos() -> None:
    """Scenario: Listar recursos disponibles."""

    reader = McpResourceReader(
        settings=_settings(), transport_factory=make_fake_transport_factory()
    )

    resources = await reader.list_resources(_ctx())

    small = next(r for r in resources if r.uri == "fake://notes/small")
    assert small.name == "small_note"
    assert small.mime_type == "text/plain"


@pytest.mark.asyncio(loop_scope="session")
async def test_read_resource_within_tope_returns_full_content() -> None:
    """Scenario: Leer un recurso dentro del tope."""

    reader = McpResourceReader(
        settings=_settings(MCP_MAX_RESOURCE_BYTES=1_048_576),
        transport_factory=make_fake_transport_factory(),
    )

    content = await reader.read_resource(_ctx(), "fake://notes/small")

    assert content.text == SMALL_RESOURCE_TEXT
    assert content.truncated is False


@pytest.mark.asyncio(loop_scope="session")
async def test_read_resource_exceeding_tope_is_rejected_without_the_full_content() -> None:
    """Scenario: Leer un recurso que excede el tope — rechazo sin exponer el
    contenido completo en el DTO devuelto."""

    reader = McpResourceReader(
        settings=_settings(MCP_MAX_RESOURCE_BYTES=LARGE_RESOURCE_BYTES // 2),
        transport_factory=make_fake_transport_factory(),
    )

    with pytest.raises(errors.McpResourceTooLargeError) as exc_info:
        await reader.read_resource(_ctx(), "fake://notes/large")

    # The oversized content NEVER leaks into the error either.
    assert "X" * 50 not in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# MC-R5 — tools con invocación controlada
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_list_tools_maps_read_only_hint() -> None:
    """Scenario: Listar tools expuestas — con su `readOnlyHint` si aplica."""

    reader = McpResourceReader(
        settings=_settings(), transport_factory=make_fake_transport_factory()
    )

    tools = await reader.list_tools(_ctx())

    read_only = next(t for t in tools if t.name == "read_only_echo")
    write_tool = next(t for t in tools if t.name == "dangerous_write")
    assert read_only.read_only is True
    assert write_tool.read_only is False


@pytest.mark.asyncio(loop_scope="session")
async def test_call_tool_allowlisted_and_read_only_executes_and_returns_result() -> None:
    """Scenario: Invocar tool allowlisted y de solo lectura."""

    reader = McpResourceReader(
        settings=_settings(), transport_factory=make_fake_transport_factory()
    )
    ctx = _ctx(tools_allowlist=frozenset({"read_only_echo"}))

    result = await reader.call_tool(ctx, "read_only_echo", {"message": "hola"})

    assert result.text == f"{READ_ONLY_TOOL_ECHO_PREFIX}: hola"


@pytest.mark.asyncio(loop_scope="session")
async def test_call_tool_not_in_allowlist_is_rejected_without_contacting_server() -> None:
    """Scenario: Tool fuera de la allowlist es rechazada — SIN contactar al
    servidor (probado inyectando un `transport_factory` que reventaría si
    se llegara a invocar)."""

    reader = McpResourceReader(
        settings=_settings(), transport_factory=_never_called_transport_factory
    )
    ctx = _ctx(tools_allowlist=frozenset({"some_other_tool"}))

    with pytest.raises(errors.McpToolNotAllowedError):
        await reader.call_tool(ctx, "read_only_echo", {"message": "hola"})


@pytest.mark.asyncio(loop_scope="session")
async def test_call_tool_allowlisted_but_write_is_rejected() -> None:
    """Scenario: Tool allowlisted sin `readOnlyHint` es rechazada — el hint
    por sí solo NUNCA es suficiente, pero tampoco la allowlist sola."""

    reader = McpResourceReader(
        settings=_settings(), transport_factory=make_fake_transport_factory()
    )
    ctx = _ctx(tools_allowlist=frozenset({"dangerous_write"}))

    with pytest.raises(errors.McpToolNotAllowedError):
        await reader.call_tool(ctx, "dangerous_write", {"payload": "boom"})


# ---------------------------------------------------------------------------
# MC-R6 — timeout y topes por llamada
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_timeout_raises_mcp_timeout_error() -> None:
    """Scenario: Timeout por llamada — la conexión queda liberada (el
    `async with` del factory nunca se abre)."""

    reader = McpResourceReader(settings=_settings(), transport_factory=timeout_transport_factory)

    with pytest.raises(errors.McpTimeoutError):
        await reader.list_resources(_ctx())


@pytest.mark.asyncio(loop_scope="session")
async def test_max_list_items_caps_the_number_of_resources_returned() -> None:
    """Scenario: Tope de tamaño/número de elementos — `MCP_MAX_LIST_ITEMS`
    respetado (el fake publica 3 recursos)."""

    reader = McpResourceReader(
        settings=_settings(MCP_MAX_LIST_ITEMS=1),
        transport_factory=make_fake_transport_factory(),
    )

    resources = await reader.list_resources(_ctx())

    assert len(resources) == 1


# ---------------------------------------------------------------------------
# MC-R8 — contenido tratado como dato inerte
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_instruction_like_content_is_returned_as_plain_data_never_executed() -> None:
    """Scenario: Contenido con texto tipo instrucción no se ejecuta — se
    retorna como texto plano dentro del DTO, nunca interpretado."""

    reader = McpResourceReader(
        settings=_settings(), transport_factory=make_fake_transport_factory()
    )

    content = await reader.read_resource(_ctx(), "fake://notes/instruction-like")

    assert content.text is not None
    assert "IGNORA TODAS LAS INSTRUCCIONES" in content.text
    assert isinstance(content.text, str)
