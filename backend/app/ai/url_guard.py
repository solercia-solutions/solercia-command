"""Anti-SSRF guard for provider base URLs (C04).

Replaces the fixed `LLM_BASE_URL_ALLOWLIST` for per-organization settings:

- External presets: only their fixed URL.
- Local presets (`ollama_local`, `llamacpp_local`): any loopback host
  (127.0.0.0/8, ::1, ``localhost``) or ``host.docker.internal``, HTTP or HTTPS.
- ``custom``: HTTPS to a host whose EVERY resolved address is public; plain
  HTTP only to an explicit loopback host. Private, link-local (cloud
  metadata), CGNAT, multicast, reserved and unspecified addresses are
  blocked, also behind IPv4-mapped IPv6 or a DNS name.

Rejections raise `LlmBaseUrlRejected` with a fixed message — the URL (which
may carry credentials) is never echoed. DNS is injectable for tests.
Residual risk: DNS rebinding between this check and the request; the check
runs on save, on the connection test and on every port build.
"""

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

from app.ai.errors import LlmBaseUrlRejected
from app.ai.presets import ProviderPreset

Resolver = Callable[[str], list[str]]

_LOOPBACK_NAMES = {"localhost"}
_DOCKER_HOST = "host.docker.internal"


def default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return sorted({str(info[4][0]) for info in infos})


def _ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _is_loopback_host(host: str) -> bool:
    if host.lower() in _LOOPBACK_NAMES:
        return True
    address = _ip(host)
    return address is not None and address.is_loopback


def is_loopback_url(url: str) -> bool:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return False
    return bool(host) and _is_loopback_host(host)


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return address.is_global and not address.is_multicast


def _parse(url: str) -> tuple[str, str]:
    """Return ``(scheme, host)`` or reject malformed / credentialed URLs."""

    try:
        parts = urlsplit(url)
        host = parts.hostname
        _ = parts.port  # raises ValueError on a non-numeric port
    except ValueError as exc:
        raise LlmBaseUrlRejected() from exc
    if parts.scheme not in ("http", "https") or not host:
        raise LlmBaseUrlRejected()
    if parts.username is not None or parts.password is not None:
        raise LlmBaseUrlRejected()
    if parts.query or parts.fragment:
        raise LlmBaseUrlRejected()
    return parts.scheme, host


def _check_custom_host(scheme: str, host: str, resolver: Resolver) -> None:
    if _is_loopback_host(host):
        return
    if scheme != "https":
        raise LlmBaseUrlRejected()
    literal = _ip(host)
    if literal is not None:
        if not _is_public(literal):
            raise LlmBaseUrlRejected()
        return
    try:
        resolved = resolver(host)
    except OSError as exc:
        raise LlmBaseUrlRejected() from exc
    addresses = [_ip(value) for value in resolved]
    if not addresses or any(a is None or not _is_public(a) for a in addresses):
        raise LlmBaseUrlRejected()


def validate_provider_base_url(
    preset: ProviderPreset,
    base_url: str | None,
    *,
    resolver: Resolver = default_resolver,
) -> str:
    """Return the normalized base URL (no trailing slash) or raise."""

    candidate = (base_url or "").strip() or (preset.base_url or "")
    normalized = candidate.rstrip("/")
    if not normalized:
        raise LlmBaseUrlRejected()
    scheme, host = _parse(normalized)

    if not preset.base_url_editable:
        if normalized != preset.base_url:
            raise LlmBaseUrlRejected()
        return normalized

    if preset.key == "custom":
        _check_custom_host(scheme, host, resolver)
        return normalized

    # Local presets: loopback or the Docker host alias only.
    if not (_is_loopback_host(host) or host.lower() == _DOCKER_HOST):
        raise LlmBaseUrlRejected()
    return normalized
