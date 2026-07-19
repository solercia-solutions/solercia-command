"""Anti-SSRF guard for an MCP server's base URL (change 19-mcp-connector,
mcp-connector/spec.md MC-R7 "Validación anti-SSRF de la URL del servidor").

``validate_mcp_url`` runs BEFORE any socket is opened toward the server —
both at connector REGISTRATION time (``app/modules/connectors/service.py``,
Lote 6) and at the START of every ephemeral session
(``adapters/mcp/session.open_session``, Lote 4, "validate_mcp_url ANTES de
abrir socket"). It returns the resolved, IP-PINNED target the caller MUST
connect to instead of re-resolving the hostname later — this is what closes
the DNS-rebinding TOCTOU gap (design.md Architecture Decisions, "IP-pin").

Model (default-deny, two independent checks — see ``app/config.py``'s
``MCP_HOST_ALLOWLIST`` docstring for the full rationale):

1. Scheme: ``http``/``https`` only; ``http`` further gated by
   ``MCP_ALLOW_HTTP`` (off in production).
2. Host: ``MCP_HOST_ALLOWLIST`` is the ONE authoritative gate — ANY host not
   literally present there is rejected, public or private. A host that IS
   allowlisted may resolve to a private/reserved range on purpose (e.g. a
   local test server) and is still permitted.
3. ``MCP_BLOCK_PRIVATE_NETWORKS`` (default on) adds a SECOND, independent
   rejection for a private/reserved resolution on a host that is NOT
   allowlisted — defense-in-depth so the allowlist is never the ONLY thing
   standing between a misconfiguration and SSRF into e.g.
   ``169.254.169.254`` (cloud metadata endpoints).
"""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.mcp.errors import McpSsrfRejected

_DEFAULT_PORT_BY_SCHEME = {"http": 80, "https": 443}


@dataclass(frozen=True)
class PinnedTarget:
    """The IP-pinned connection target a validated MCP base URL resolves
    to — the caller (``session.py``) connects to ``ip``, never re-resolving
    ``host`` at connect time."""

    scheme: str
    host: str
    port: int
    ip: str


def _is_private_or_reserved(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        # Unparsable — fail closed, never treat an address we cannot even
        # classify as "safe".
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def _resolve_first_ip(host: str, port: int) -> str:
    running_loop = asyncio.get_running_loop()
    try:
        infos = await running_loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise McpSsrfRejected(
            f"No fue posible resolver el host del servidor MCP: {host!r}.",
            code="mcp_host_unresolved",
        ) from exc
    if not infos:
        raise McpSsrfRejected(
            f"El host del servidor MCP no resolvió a ninguna dirección: {host!r}.",
            code="mcp_host_unresolved",
        )
    resolved_address = infos[0][4][0]
    return str(resolved_address)


async def validate_mcp_url(url: str, *, settings: Settings = default_settings) -> PinnedTarget:
    """Validate ``url`` against the anti-SSRF guard and return the
    IP-pinned :class:`PinnedTarget` to connect to.

    Raises :class:`McpSsrfRejected` (422) for any rejected URL — a
    configuration error, never a transient one.
    """

    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise McpSsrfRejected(
            f"Esquema de URL no soportado para un servidor MCP: {parsed.scheme!r}.",
            code="mcp_scheme_invalid",
        )
    if parsed.scheme == "http" and not settings.MCP_ALLOW_HTTP:
        raise McpSsrfRejected(
            "El servidor MCP debe usar https:// en este entorno.",
            code="mcp_http_not_allowed",
        )

    host = parsed.hostname
    if not host:
        raise McpSsrfRejected(
            "La URL del servidor MCP no tiene un host válido.",
            code="mcp_host_missing",
        )
    port = parsed.port or _DEFAULT_PORT_BY_SCHEME[parsed.scheme]

    allowlisted = host in settings.MCP_HOST_ALLOWLIST
    ip = await _resolve_first_ip(host, port)

    if settings.MCP_BLOCK_PRIVATE_NETWORKS and not allowlisted and _is_private_or_reserved(ip):
        raise McpSsrfRejected(
            f"El host {host!r} resuelve a un rango de red privado/reservado "
            "y no está en la allowlist.",
            code="mcp_private_network_blocked",
        )
    if not allowlisted:
        raise McpSsrfRejected(
            f"El host {host!r} no está en MCP_HOST_ALLOWLIST.",
            code="mcp_host_not_allowlisted",
        )

    return PinnedTarget(scheme=parsed.scheme, host=host, port=port, ip=ip)
