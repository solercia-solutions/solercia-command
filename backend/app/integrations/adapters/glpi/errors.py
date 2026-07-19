"""GLPI -> domain error mapping (change 17-adapter-glpi, design.md
"errors.py"). Every controlled failure the adapter raises toward its
callers is an ``AppException`` subclass — the same convention the rest of
the app uses (``app/shared/exceptions.py``) — so nothing downstream needs
an adapter-specific error type to handle a `glpi` failure.

NEVER interpolate a token (App-Token/user_token/session_token) into any
message built here — these strings ARE what a caller may log or surface to
the user (GA-R6, "sin credenciales ni tokens en el mensaje").
"""

from app.shared.exceptions import AppException

_UNAVAILABLE_MESSAGE = (
    "GLPI no está disponible en este momento. Inténtalo de nuevo más tarde."
)
_AUTH_MESSAGE = (
    "Las credenciales de GLPI no son válidas o fueron revocadas. Verifica "
    "el App-Token y el user_token del conector."
)


class GlpiUnavailable(AppException):
    """GLPI is unreachable (timeout/network error) or returned a
    transient/unexpected failure unrelated to authentication — retryable,
    RETRYABLE from the caller's perspective (GA-R6, "GLPI no responde")."""

    def __init__(self, detail: str = _UNAVAILABLE_MESSAGE) -> None:
        super().__init__(detail, code="glpi_unavailable", status_code=503)


class GlpiAuthError(AppException):
    """GLPI rejected the App-Token/user_token (``initSession`` failed, or a
    reinit-after-401 also failed) — never retried automatically beyond
    ``session.py``'s single reinit attempt; reconnecting the connector is
    required (GA-R6, "Credenciales inválidas")."""

    def __init__(self, detail: str = _AUTH_MESSAGE) -> None:
        super().__init__(detail, code="glpi_auth_error", status_code=401)
