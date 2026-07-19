"""Graph → domain error mapping (change 15-adapter-microsoft365, design.md
"errors.py"). Every controlled failure the adapter raises toward its
callers is an ``AppException`` — the same convention the rest of the app
uses (``app/shared/exceptions.py``) — so nothing downstream needs an
adapter-specific error type to handle a `microsoft365` failure. Messages
are written in Colombian formal Spanish (tuteo), same as every other
user-facing error in the app.

NEVER interpolate a token (access/refresh) into any message built here —
these strings ARE what a caller may log or surface to the user.
"""

from app.shared.exceptions import AppException


def capability_unavailable(
    detail: str = (
        "Esta funcionalidad de Microsoft 365 no está disponible para esta "
        "cuenta conectada."
    ),
) -> AppException:
    """The tenant/account never granted the scope this capability needs
    (e.g. transcripciones sin admin consent) — a controlled degradation,
    never a crash (M365-R6)."""

    return AppException(detail, code="capability_unavailable", status_code=403)


def provider_throttled(
    detail: str = (
        "Microsoft Graph está limitando las solicitudes en este momento. "
        "Inténtalo de nuevo más tarde."
    ),
) -> AppException:
    """Graph kept responding ``429`` past ``M365_MAX_RETRIES`` (M365-R7)."""

    return AppException(detail, code="provider_throttled", status_code=503)


def provider_unavailable(
    detail: str = (
        "El servicio de Microsoft Graph no está disponible en este "
        "momento. Inténtalo de nuevo más tarde."
    ),
) -> AppException:
    """Graph is unreachable or returned a 5xx unrelated to throttling."""

    return AppException(detail, code="provider_unavailable", status_code=503)


def oauth_token_invalid(
    detail: str = (
        "La conexión con Microsoft 365 expiró o fue revocada. Debes "
        "reconectar la cuenta."
    ),
) -> AppException:
    """The access token expired AND the refresh attempt also failed (no
    refresh token, or Graph rejected it as revoked) — reconnection is
    required, never an automatic retry loop (M365-R3)."""

    return AppException(detail, code="oauth_token_invalid", status_code=401)
