"""Google → domain error mapping (change 16-adapter-google, design.md
"errors.py", espejo del 15 — same taxonomy as
``adapters/microsoft365/errors.py``). Every controlled failure the adapter
raises toward its callers is an ``AppException`` (``app/shared/exceptions.py``),
so nothing downstream needs a Google-specific error type. Messages are
written in Colombian formal Spanish (tuteo), same as every other
user-facing error in the app.

:func:`error_for_response` is the ONE pure status-code(+body) → domain
error mapping this adapter uses — ``client.py`` (Lote 2) is its only
runtime caller, but it has zero HTTP/network dependency itself so it is
directly unit-testable before ``client.py`` exists (Lote 1).

NEVER interpolate a token (access/refresh) into any message built here —
these strings ARE what a caller may log or surface to the user.
"""

from typing import Any

from app.shared.exceptions import AppException

# Google's `error.errors[].reason` values that mean "throttled, retry with
# backoff" — as opposed to any OTHER 403 reason, which means the connected
# account genuinely lacks permission (`capability_unavailable`).
_THROTTLE_REASONS = frozenset({"rateLimitExceeded", "userRateLimitExceeded"})


def capability_unavailable(
    detail: str = (
        "Esta funcionalidad de Google Workspace no está disponible para "
        "esta cuenta conectada."
    ),
) -> AppException:
    """The connected account lacks permission for the resource requested
    (e.g. sin acceso al Drive del organizador para `meeting_notes`) — a
    controlled degradation, never a crash (GA-R7)."""

    return AppException(detail, code="capability_unavailable", status_code=403)


def provider_throttled(
    detail: str = (
        "Google está limitando las solicitudes en este momento. Inténtalo "
        "de nuevo más tarde."
    ),
) -> AppException:
    """Google kept responding `429`/`403 rateLimitExceeded` past
    `GOOGLE_MAX_RETRIES` (GA-R3)."""

    return AppException(detail, code="provider_throttled", status_code=503)


def provider_unavailable(
    detail: str = (
        "El servicio de Google no está disponible en este momento. "
        "Inténtalo de nuevo más tarde."
    ),
) -> AppException:
    """Google is unreachable or returned a `5xx` unrelated to throttling
    (RETRYABLE — a transient outage on Google's side)."""

    return AppException(detail, code="provider_unavailable", status_code=503)


def provider_request_failed(
    detail: str = (
        "Google rechazó la solicitud. Revisa la configuración del conector "
        "antes de intentarlo de nuevo."
    ),
) -> AppException:
    """Google responded a `4xx` OTHER than `401`/`403`/`429` (e.g.
    `400`/`404`) — a malformed/invalid request, NOT a transient outage.
    Distinct from `provider_unavailable`: never suggests retrying as-is."""

    return AppException(detail, code="provider_request_failed", status_code=502)


def oauth_token_invalid(
    detail: str = (
        "La conexión con Google expiró o fue revocada. Debes reconectar la "
        "cuenta."
    ),
) -> AppException:
    """The access token expired AND the refresh attempt also failed (no
    refresh token, or Google rejected it as revoked) — reconnection is
    required, never an automatic retry loop (GA-R3)."""

    return AppException(detail, code="oauth_token_invalid", status_code=401)


def _403_reason(body: dict[str, Any] | None) -> str | None:
    """Extract Google's `error.errors[0].reason` from a parsed `403` body,
    or `None` when the body is absent/unparseable."""

    if not body:
        return None
    error_list = (body.get("error") or {}).get("errors") or []
    if not error_list:
        return None
    reason = error_list[0].get("reason")
    return str(reason) if reason is not None else None


def error_for_response(
    status_code: int, body: dict[str, Any] | None = None
) -> AppException:
    """Map a raw Google API HTTP `status_code` (+ optional parsed JSON
    `body`) to the matching domain :class:`AppException` — pure, no I/O.
    ``client.py`` is the ONLY caller that actually issues the HTTP request
    this maps a response FROM (design.md Data Flow); kept here, standalone,
    so the mapping itself is unit-tested before `client.py` exists."""

    if status_code == 401:
        return oauth_token_invalid()
    if status_code == 429:
        return provider_throttled()
    if status_code == 403:
        if _403_reason(body) in _THROTTLE_REASONS:
            return provider_throttled()
        return capability_unavailable()
    if status_code >= 500:
        return provider_unavailable()
    return provider_request_failed()
