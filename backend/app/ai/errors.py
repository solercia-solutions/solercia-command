"""`LlmPort` -> domain error taxonomy (change 48-puerto-llm, design.md
"Taxonomía de errores", mirrors `jira/errors.py`). Every subclass carries a
stable `code`; `app/shared/exceptions.py` converts it into
`{detail, code, status}`. NEVER interpolate `LLM_API_KEY`/`LLM_BASE_URL`
into a message here (spec `llm-port`, "Protección de secretos").
"""

from app.shared.exceptions import AppException

_UNAVAILABLE = "El proveedor de IA no está disponible. Inténtalo de nuevo más tarde."
_AUTH = "Las credenciales del proveedor de IA no son válidas o fueron revocadas."
_RATE_LIMITED = "El proveedor de IA está limitando la tasa de solicitudes. Inténtalo más tarde."
_TIMEOUT = "El proveedor de IA tardó demasiado en responder."
_INVALID_OUTPUT = "El proveedor de IA devolvió una respuesta ilegible."
_SCHEMA_MISMATCH = "La respuesta del proveedor de IA no cumple el esquema esperado."
_CONTENT_FILTERED = "El proveedor de IA rechazó generar una respuesta para esta solicitud."
_CONFIG_INVALID = "La configuración del proveedor de IA no es válida. Verifica las `LLM_*`."


class LlmAuthorizationRequired(AppException):
    """No trusted authorization context exists in the current request contract.

    Temporary deny-all barrier for real AI calls, not a legal classification.
    No caller-provided detail is accepted, so payload/provider text stays out.
    """

    def __init__(self) -> None:
        super().__init__(
            "No se realizó la llamada de IA: falta autorización verificable para esta operación.",
            code="llm_authorization_required",
            status_code=403,
        )


class LlmUnavailable(AppException):
    def __init__(self, detail: str = _UNAVAILABLE) -> None:
        super().__init__(detail, code="llm_unavailable", status_code=503)


class LlmAuthError(AppException):
    """`LLM_API_KEY` rechazada (`401`/`403`); la clave nunca aparece aquí."""

    def __init__(self, detail: str = _AUTH) -> None:
        super().__init__(detail, code="llm_auth_error", status_code=401)


class LlmRateLimited(AppException):
    def __init__(self, detail: str = _RATE_LIMITED) -> None:
        super().__init__(detail, code="llm_rate_limited", status_code=503)


class LlmTimeout(AppException):
    def __init__(self, detail: str = _TIMEOUT) -> None:
        super().__init__(detail, code="llm_timeout", status_code=503)


class LlmInvalidOutput(AppException):
    """Cuerpo ilegible — distinto de `LlmSchemaMismatch` (JSON legible,
    forma incorrecta)."""

    def __init__(self, detail: str = _INVALID_OUTPUT) -> None:
        super().__init__(detail, code="llm_invalid_output", status_code=502)


class LlmSchemaMismatch(AppException):
    """`output_schema.model_validate(...)` falló; `parsed` nunca se
    devuelve sin validar (design.md D7)."""

    def __init__(self, detail: str = _SCHEMA_MISMATCH) -> None:
        super().__init__(detail, code="llm_schema_mismatch", status_code=502)


class LlmContentFiltered(AppException):
    def __init__(self, detail: str = _CONTENT_FILTERED) -> None:
        super().__init__(detail, code="llm_content_filtered", status_code=422)


class LlmConfigInvalid(AppException):
    """Proveedor desconocido, `LLM_BASE_URL` fuera de la allowlist o clave
    vacía — el valor inválido nunca se nombra."""

    def __init__(self, detail: str = _CONFIG_INVALID) -> None:
        super().__init__(detail, code="llm_config_invalid", status_code=422)
