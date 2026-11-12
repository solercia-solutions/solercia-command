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
   literally present there is rejected, public or private, BEFORE any DNS
   lookup is even attempted. A host that IS allowlisted may resolve to a
   private/reserved range on purpose (e.g. a local test server) and is
   still permitted.
3. Because a non-allowlisted host is now rejected WITHOUT ever resolving it,
   ``MCP_BLOCK_PRIVATE_NETWORKS``'s only remaining branch never applies —
   the allowlist alone already settles that host's fate. Kept for
   ``Settings`` shape/backward compatibility; presently a no-op.
4. Resolution itself is bounded by ``MCP_DNS_TIMEOUT_SECONDS`` (default 5s)
   — a hanging/malicious resolver for an ALLOWLISTED host can no longer
   stall the caller indefinitely.
"""

import asyncio
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


async def _resolve_first_ip(host: str, port: int, *, timeout: float) -> str:
    running_loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            running_loop.getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout=timeout
        )
    except TimeoutError as exc:
        raise McpSsrfRejected(
            f"Tiempo de espera agotado al resolver el host del servidor MCP: {host!r}.",
            code="mcp_host_resolution_timeout",
        ) from exc
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

    if host not in settings.MCP_HOST_ALLOWLIST:
        # Rejected WITHOUT ever resolving DNS (judgment-day 4R CRITICAL fix:
        # the allowlist gate now runs strictly BEFORE any lookup, closing
        # the no-timeout-DNS-against-an-attacker-controlled-name surface for
        # every non-allowlisted host).
        raise McpSsrfRejected(
            f"El host {host!r} no está en MCP_HOST_ALLOWLIST.",
            code="mcp_host_not_allowlisted",
        )

    ip = await _resolve_first_ip(host, port, timeout=settings.MCP_DNS_TIMEOUT_SECONDS)

    return PinnedTarget(scheme=parsed.scheme, host=host, port=port, ip=ip)
