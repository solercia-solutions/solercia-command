"""RED tests for the MCP adapter's anti-SSRF guard (change 19-mcp-connector,
Lote 3, mcp-connector/spec.md MC-R7 "Validación anti-SSRF de la URL del
servidor").

``validate_mcp_url`` is a pure(-ish) async function — `getaddrinfo` is the
only I/O, and every host used here is a LITERAL IP address (never a hostname
that needs real DNS), so the whole suite runs with zero real network calls
(design.md Testing Strategy, "pytest puro; `getaddrinfo` con IPs literales").

Mirrors ``test_adapter_glpi.py``'s ``_settings(**overrides)`` precedent: a
REAL ``Settings`` instance built with just the ``MCP_*`` overrides a given
scenario needs, injected explicitly — never a monkeypatch of the global
singleton.
"""

import pytest

from app.config import Settings


def _settings(**overrides: object) -> Settings:
    """Build a real `Settings` instance with `MCP_*` overrides for a test."""

    defaults: dict[str, object] = {
        "MCP_HOST_ALLOWLIST": ["127.0.0.1"],
        "MCP_ALLOW_HTTP": True,
        "MCP_BLOCK_PRIVATE_NETWORKS": True,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# MC-R7 — host fuera de la allowlist, con o sin rango privado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_host_outside_allowlist_is_rejected_even_if_public() -> None:
    """Scenario (default-deny): un host PÚBLICO (`8.8.8.8`, literal — sin
    DNS real) que NO está en `MCP_HOST_ALLOWLIST` se rechaza igual — la
    allowlist gobierna TODO host, no solo los privados."""

    from app.integrations.adapters.mcp.errors import McpSsrfRejected
    from app.integrations.adapters.mcp.ssrf import validate_mcp_url

    settings = _settings(MCP_HOST_ALLOWLIST=["allowed.example.test"])

    with pytest.raises(McpSsrfRejected) as exc_info:
        await validate_mcp_url("https://8.8.8.8/mcp", settings=settings)

    assert exc_info.value.code == "mcp_host_not_allowlisted"
    assert exc_info.value.status_code == 422


@pytest.mark.parametrize(
    "private_host",
    ["127.0.0.1", "10.1.2.3", "192.168.1.5", "169.254.1.1", "::1", "fd00::1"],
)
@pytest.mark.asyncio(loop_scope="session")
async def test_private_or_reserved_hosts_rejected_by_default_without_allowlist(
    private_host: str,
) -> None:
    """Scenario: URL privada sin allowlist es rechazada — `127.0.0.1`/
    `10.*`/`192.168.*`/`169.254.*`/`::1`/`fc00::/7` rechazados por defecto
    cuando el host NO está explícitamente en `MCP_HOST_ALLOWLIST`."""

    from app.integrations.adapters.mcp.errors import McpSsrfRejected
    from app.integrations.adapters.mcp.ssrf import validate_mcp_url

    settings = _settings(MCP_HOST_ALLOWLIST=["allowed.example.test"])
    host = f"[{private_host}]" if ":" in private_host else private_host

    with pytest.raises(McpSsrfRejected) as exc_info:
        await validate_mcp_url(f"https://{host}/mcp", settings=settings)

    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# MC-R7 — host explícitamente allowlisted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_host_in_explicit_allowlist_is_permitted_even_if_it_resolves_privately() -> None:
    """Scenario: Host en la allowlist explícita es permitido — aunque
    `127.0.0.1` resuelve a un rango privado, está explícitamente confiado
    por el admin en `MCP_HOST_ALLOWLIST`."""

    from app.integrations.adapters.mcp.ssrf import validate_mcp_url

    settings = _settings(MCP_HOST_ALLOWLIST=["127.0.0.1"])

    pinned = await validate_mcp_url("https://127.0.0.1:9443/mcp", settings=settings)

    assert pinned.host == "127.0.0.1"
    assert pinned.ip == "127.0.0.1"
    assert pinned.port == 9443
    assert pinned.scheme == "https"


@pytest.mark.asyncio(loop_scope="session")
async def test_private_network_block_disabled_still_requires_allowlist() -> None:
    """`MCP_BLOCK_PRIVATE_NETWORKS=False` only removes the SECOND,
    defense-in-depth private-range check — the allowlist gate itself is
    NEVER optional; a non-allowlisted host is still rejected."""

    from app.integrations.adapters.mcp.errors import McpSsrfRejected
    from app.integrations.adapters.mcp.ssrf import validate_mcp_url

    settings = _settings(
        MCP_HOST_ALLOWLIST=["allowed.example.test"], MCP_BLOCK_PRIVATE_NETWORKS=False
    )

    with pytest.raises(McpSsrfRejected) as exc_info:
        await validate_mcp_url("https://10.0.0.9/mcp", settings=settings)

    assert exc_info.value.code == "mcp_host_not_allowlisted"


# ---------------------------------------------------------------------------
# MC-R7 — esquema http/https
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_http_rejected_when_allow_http_is_off() -> None:
    """Scenario: `http` rechazado en producción — `MCP_ALLOW_HTTP=False`
    (el valor de producción) rechaza cualquier URL `http://`, incluso hacia
    un host allowlisted."""

    from app.integrations.adapters.mcp.errors import McpSsrfRejected
    from app.integrations.adapters.mcp.ssrf import validate_mcp_url

    settings = _settings(MCP_HOST_ALLOWLIST=["127.0.0.1"], MCP_ALLOW_HTTP=False)

    with pytest.raises(McpSsrfRejected) as exc_info:
        await validate_mcp_url("http://127.0.0.1/mcp", settings=settings)

    assert exc_info.value.code == "mcp_http_not_allowed"


@pytest.mark.asyncio(loop_scope="session")
async def test_https_always_permitted_regardless_of_allow_http() -> None:
    """Scenario: `https://` permitido — el toggle `MCP_ALLOW_HTTP` nunca
    afecta un esquema `https`."""

    from app.integrations.adapters.mcp.ssrf import validate_mcp_url

    settings = _settings(MCP_HOST_ALLOWLIST=["127.0.0.1"], MCP_ALLOW_HTTP=False)

    pinned = await validate_mcp_url("https://127.0.0.1/mcp", settings=settings)

    assert pinned.scheme == "https"


@pytest.mark.asyncio(loop_scope="session")
async def test_http_permitted_when_allow_http_is_on() -> None:
    """`MCP_ALLOW_HTTP=True` (dev/test default) permits `http://` toward an
    allowlisted host."""

    from app.integrations.adapters.mcp.ssrf import validate_mcp_url

    settings = _settings(MCP_HOST_ALLOWLIST=["127.0.0.1"], MCP_ALLOW_HTTP=True)

    pinned = await validate_mcp_url("http://127.0.0.1/mcp", settings=settings)

    assert pinned.scheme == "http"


@pytest.mark.asyncio(loop_scope="session")
async def test_unsupported_scheme_is_rejected() -> None:
    """A scheme other than http/https (e.g. `ftp://`) is rejected before any
    allowlist/DNS check."""

    from app.integrations.adapters.mcp.errors import McpSsrfRejected
    from app.integrations.adapters.mcp.ssrf import validate_mcp_url

    settings = _settings(MCP_HOST_ALLOWLIST=["127.0.0.1"])

    with pytest.raises(McpSsrfRejected) as exc_info:
        await validate_mcp_url("ftp://127.0.0.1/mcp", settings=settings)

    assert exc_info.value.code == "mcp_scheme_invalid"
