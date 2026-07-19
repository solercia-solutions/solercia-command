"""Jira -> domain error mapping (change 18-adapter-jira, mirrors
``app/integrations/adapters/glpi/errors.py``). Every controlled failure
this adapter raises toward its callers is an ``AppException`` subclass
with a stable ``code`` — nothing downstream needs a Jira-specific type to
handle a ``jira`` failure.

NEVER interpolate an ``email``/``api_token`` into any message built here —
these strings ARE what a caller may log or surface to the user (Threat
Matrix, "Secreto api_token nunca expuesto").
"""

from app.shared.exceptions import AppException

_FILE_FORMAT_MESSAGE = (
    "El archivo no tiene el formato esperado. Verifica las columnas requeridas."
)
_FILE_TOO_LARGE_MESSAGE = (
    "El archivo excede el límite permitido de filas o celdas. Divide la "
    "exportación en archivos más pequeños."
)


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
