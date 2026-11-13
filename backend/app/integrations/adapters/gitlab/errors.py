"""GitLab -> domain error mapping (mirrors ``adapters/jira/errors.py``).

Every controlled failure is an ``AppException`` with a stable ``code``.
NEVER interpolate the access token into any message built here: these
strings are what a caller may log or show to the user.

Provider-side credential rejections answer ``422`` (not ``401``): a ``401``
from Command's own API means "your Command session expired" to the
frontend's auth interceptor, which would refresh and retry instead of
showing the message.
"""

from collections.abc import Iterable

from app.shared.exceptions import AppException

_AUTH_MESSAGE = (
    "GitLab rechazó el token de acceso: no es válido, venció o fue revocado. "
    "Verifica el token del conector."
)
_CONFIG_MESSAGE = (
    "La dirección de GitLab no es válida o no está permitida. Debe usar https "
    "y su servidor debe estar en GITLAB_BASE_URL_ALLOWLIST."
)
_INCOMPLETE_MESSAGE = "Faltan base_url o access_token para validar el token de GitLab."
_SCOPE_MISSING_MESSAGE = (
    "El token de GitLab no tiene el alcance read_api. Crea un token con read_api "
    "para que Solercia Command pueda leer los repositorios."
)
_UNAVAILABLE_MESSAGE = "GitLab no está disponible en este momento. Inténtalo de nuevo más tarde."
_RATE_LIMITED_MESSAGE = (
    "GitLab está limitando la tasa de solicitudes. Inténtalo de nuevo más tarde."
)
_REQUEST_FAILED_MESSAGE = (
    "GitLab rechazó la solicitud. Verifica que el token tenga acceso al repositorio."
)
_NOT_FOUND_MESSAGE = "El repositorio de GitLab no existe o el token no tiene acceso a él."
_NOT_INSPECTABLE_MESSAGE = (
    "GitLab no permitió consultar los alcances del token (GET "
    "/personal_access_tokens/self). Puede deberse a una versión antigua de GitLab "
    "o a un tipo de token que no admite esa consulta. Usa un token personal, de "
    "grupo o de proyecto con el alcance read_api en una versión reciente de GitLab."
)


class GitlabAuthError(AppException):
    """GitLab answered ``401`` or reported the token as inactive."""

    def __init__(self, detail: str = _AUTH_MESSAGE) -> None:
        super().__init__(detail, code="gitlab_auth_error", status_code=422)


class GitlabConfigInvalid(AppException):
    """``base_url`` is not ``https`` or its host is outside the allowlist —
    raised before any HTTP request is attempted (anti-SSRF)."""

    def __init__(self, detail: str = _CONFIG_MESSAGE) -> None:
        super().__init__(detail, code="gitlab_config_invalid", status_code=422)


class GitlabCredentialsIncomplete(AppException):
    """The credential payload lacks ``base_url`` or ``access_token``."""

    def __init__(self, detail: str = _INCOMPLETE_MESSAGE) -> None:
        super().__init__(detail, code="gitlab_credentials_incomplete", status_code=422)


class GitlabTokenScopeMissing(AppException):
    """The token does not carry ``read_api``."""

    def __init__(self, detail: str = _SCOPE_MISSING_MESSAGE) -> None:
        super().__init__(detail, code="gitlab_token_scope_missing", status_code=422)


class GitlabTokenScopeNotAllowed(AppException):
    """The token carries at least one scope outside the read-only allowlist
    — only read-only tokens are accepted, so it is never persisted."""

    def __init__(self, scopes: Iterable[str]) -> None:
        listed = ", ".join(sorted(scopes))
        super().__init__(
            "El token de GitLab tiene alcances que no son de solo lectura "
            f"({listed}). Crea un token de solo lectura con el alcance read_api.",
            code="gitlab_token_scope_not_allowed",
            status_code=422,
        )


class GitlabUnavailable(AppException):
    """Timeout, network error or 5xx — retryable from the caller's side."""

    def __init__(self, detail: str = _UNAVAILABLE_MESSAGE) -> None:
        super().__init__(detail, code="gitlab_unavailable", status_code=503)


class GitlabRateLimited(AppException):
    """``429`` past ``GITLAB_MAX_RETRIES``."""

    def __init__(self, detail: str = _RATE_LIMITED_MESSAGE) -> None:
        super().__init__(detail, code="gitlab_rate_limited", status_code=503)


class GitlabRequestFailed(AppException):
    """Any other non-retryable ``4xx`` (403, 400...)."""

    def __init__(self, detail: str = _REQUEST_FAILED_MESSAGE) -> None:
        super().__init__(detail, code="gitlab_request_failed", status_code=502)


class GitlabNotFound(AppException):
    """``404``: the project does not exist or the token cannot see it."""

    def __init__(self, detail: str = _NOT_FOUND_MESSAGE) -> None:
        super().__init__(detail, code="gitlab_repository_not_found", status_code=422)


class GitlabTokenNotInspectable(AppException):
    """``GET /personal_access_tokens/self`` answered ``404``: the token's
    scopes cannot be read, so it cannot be accepted as read-only."""

    def __init__(self, detail: str = _NOT_INSPECTABLE_MESSAGE) -> None:
        super().__init__(detail, code="gitlab_token_not_inspectable", status_code=422)
