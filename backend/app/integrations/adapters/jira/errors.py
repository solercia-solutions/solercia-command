"""Jira -> domain error mapping (change 18-adapter-jira, mirrors
``app/integrations/adapters/glpi/errors.py``). Every controlled failure
this adapter raises toward its callers is an ``AppException`` subclass
with a stable ``code`` — nothing downstream needs a Jira-specific type to
handle a ``jira`` failure.

NEVER interpolate an ``email``/``api_token`` into any message built here —
these strings ARE what a caller may log or surface to the user (Threat
Matrix, "Secreto api_token nunca expuesto").
"""

from app.integrations.adapters.jira.dtos import NormalizationReport, NormalizedJiraIssue
from app.shared.exceptions import AppException

_FILE_FORMAT_MESSAGE = (
    "El archivo no tiene el formato esperado. Verifica las columnas requeridas."
)
_FILE_TOO_LARGE_MESSAGE = (
    "El archivo excede el límite permitido de filas o celdas. Divide la "
    "exportación en archivos más pequeños."
)
_UNAVAILABLE_MESSAGE = (
    "Jira no está disponible en este momento. Inténtalo de nuevo más tarde."
)
_AUTH_MESSAGE = (
    "Las credenciales de Jira no son válidas o fueron revocadas. Verifica "
    "el correo y el API token del conector."
)
_CONFIG_MESSAGE = (
    "La configuración del conector Jira (base_url) no es válida o no está "
    "permitida. Debe ser un sitio *.atlassian.net."
)
_RATE_LIMITED_MESSAGE = (
    "Jira está limitando la tasa de solicitudes. Inténtalo de nuevo más tarde."
)
_REQUEST_FAILED_MESSAGE = "Jira rechazó la solicitud. Verifica los parámetros enviados."


class JiraFileFormatError(AppException):
    """The uploaded CSV/XLSX is missing a required column (e.g. "Issue
    key") or its structure/extension is not recognizable — never
    processed partially (specs/jira-import/spec.md "Archivo malformado se
    rechaza con error controlado")."""

    def __init__(
        self,
        detail: str = _FILE_FORMAT_MESSAGE,
        *,
        missing_columns: tuple[str, ...] = (),
    ) -> None:
        super().__init__(detail, code="jira_file_format_invalid", status_code=422)
        self.missing_columns = missing_columns


class JiraFileTooLarge(AppException):
    """The uploaded file exceeds ``JIRA_FILE_MAX_ROWS``/
    ``JIRA_FILE_MAX_CELLS`` — rejected BEFORE finishing the read (Threat
    Matrix, "Bomba de descompresión XLSX")."""

    def __init__(self, detail: str = _FILE_TOO_LARGE_MESSAGE) -> None:
        super().__init__(detail, code="jira_file_too_large", status_code=422)


_FILE_INVALID_MESSAGE = "El archivo no tiene un formato CSV/XLSX válido."


class JiraFileInvalidError(AppException):
    """The uploaded bytes are not decodable as the claimed format at all —
    a non-UTF-8 "CSV" or a non-zip "XLSX" (corrupted or mislabeled file).
    Distinct from :class:`JiraFileFormatError` (readable file, wrong
    columns): here the CONTENT itself is unreadable, so parsing never
    starts."""

    def __init__(self, detail: str = _FILE_INVALID_MESSAGE) -> None:
        super().__init__(detail, code="jira_file_invalid", status_code=422)


class JiraUnavailable(AppException):
    """Jira is unreachable (timeout/network error) or returned an
    unexpected 5xx — RETRYABLE from the caller's perspective (mirrors
    ``GlpiUnavailable``)."""

    def __init__(self, detail: str = _UNAVAILABLE_MESSAGE) -> None:
        super().__init__(detail, code="jira_unavailable", status_code=503)


class JiraAuthError(AppException):
    """Jira rejected the ``email``/``api_token`` pair (``401``) —
    specs/jira-import/spec.md "Credencial inválida se rechaza sin exponer
    el secreto": the token NEVER appears in this message."""

    def __init__(self, detail: str = _AUTH_MESSAGE) -> None:
        super().__init__(detail, code="jira_auth_error", status_code=401)


class JiraConfigInvalid(AppException):
    """The connector's ``settings.jira.base_url`` failed
    :class:`~app.integrations.adapters.jira.client.JiraConfigError`'s
    constructor validation (host outside ``*.atlassian.net``, Threat
    Matrix "Anti-SSRF") — a CONFIGURATION error, never transient, so it
    surfaces as a structured ``422`` instead of an unhandled ``500``."""

    def __init__(self, detail: str = _CONFIG_MESSAGE) -> None:
        super().__init__(detail, code="jira_config_invalid", status_code=422)


class JiraRateLimited(AppException):
    """Jira answered ``429`` past ``JIRA_MAX_RETRIES`` —
    specs/jira-import/spec.md "Reintentos agotados": the caller (pagination
    loop, ``client.list_issues``) attaches every issue already fetched from
    PREVIOUS pages via ``partial_issues`` so a partially successful
    extraction is never silently discarded."""

    def __init__(
        self,
        detail: str = _RATE_LIMITED_MESSAGE,
        *,
        partial_issues: list[dict] | None = None,
    ) -> None:
        super().__init__(detail, code="jira_rate_limited", status_code=503)
        self.partial_issues: list[dict] = partial_issues if partial_issues is not None else []
        # Filled in by `JiraAdapter.import_issues` once caught mid-pagination
        # — `JiraImportService` reads these to answer 200 with
        # `truncated=true` instead of discarding them.
        self.normalized_partial_issues: list[NormalizedJiraIssue] = []
        self.partial_report: NormalizationReport | None = None


class JiraRequestFailed(AppException):
    """Jira rejected the request with a non-retryable ``4xx`` other than
    ``401``/``429`` (mirrors ``GraphClient``'s ``provider_request_failed``,
    change 15's 4xx/5xx split)."""

    def __init__(self, detail: str = _REQUEST_FAILED_MESSAGE) -> None:
        super().__init__(detail, code="jira_request_failed", status_code=502)
