"""``mcp`` -> domain error mapping (change 19-mcp-connector, design.md
"errors.py" precedent — mirrors ``adapters/glpi/errors.py``/
``adapters/jira/errors.py``). Every controlled failure the adapter raises
toward its callers is an ``AppException`` subclass, the same convention the
rest of the app uses (``app/shared/exceptions.py``).

NEVER interpolate a token/credential into any message built here — these
strings ARE what a caller may log or surface to the user
(mcp-connector/spec.md MC-R10, "el token nunca aparece ... en ningún log").
"""

from app.shared.exceptions import AppException

_SSRF_MESSAGE = (
    "La URL del servidor MCP no está permitida (validación anti-SSRF)."
)
_UNREACHABLE_MESSAGE = "El servidor MCP no está disponible en este momento."
_TIMEOUT_MESSAGE = "El servidor MCP no respondió dentro del tiempo configurado."
_TOO_LARGE_MESSAGE = "El recurso solicitado excede el tope de tamaño configurado."
_TOOL_NOT_ALLOWED_MESSAGE = "La tool solicitada no está permitida para este conector."
_OPERATION_MESSAGE = "El servidor MCP reportó un error al procesar la solicitud."


class McpSsrfRejected(AppException):
    """The server's base URL failed the anti-SSRF guard (``ssrf.py``) —
    scheme not allowed, host outside ``MCP_HOST_ALLOWLIST``, or resolves to
    a blocked private/reserved network range (mcp-connector/spec.md MC-R7).
    A CONFIGURATION error, never transient — 422, never an unhandled 500."""

    def __init__(self, detail: str = _SSRF_MESSAGE, *, code: str = "mcp_ssrf_rejected") -> None:
        super().__init__(detail, code=code, status_code=422)


class McpServerUnreachableError(AppException):
    """The MCP server could not be reached at ``initialize`` time (network
    error, connection refused) — retryable from the caller's perspective
    (MC-R3)."""

    def __init__(self, detail: str = _UNREACHABLE_MESSAGE) -> None:
        super().__init__(detail, code="mcp_server_unreachable", status_code=503)


class McpTimeoutError(AppException):
    """Any MCP operation exceeded its configured timeout — the connection is
    released, never left dangling (MC-R6)."""

    def __init__(self, detail: str = _TIMEOUT_MESSAGE) -> None:
        super().__init__(detail, code="mcp_timeout", status_code=504)


class McpResourceTooLargeError(AppException):
    """``read_resource``'s response exceeded ``MCP_MAX_RESOURCE_BYTES`` — the
    oversized content is NEVER mapped into the returned DTO (MC-R4)."""

    def __init__(self, detail: str = _TOO_LARGE_MESSAGE) -> None:
        super().__init__(detail, code="mcp_resource_too_large", status_code=422)


class McpToolNotAllowedError(AppException):
    """``call_tool`` was rejected by the default-deny enforcement (name not
    in the connector's allowlist, or allowlisted but not ``readOnlyHint:
    true``) — MC-R5. Deliberately the SAME error/code for both reasons: the
    caller never learns whether a name is "unknown" or "known but denied",
    which would otherwise leak the allowlist's exact shape."""

    def __init__(self, detail: str = _TOOL_NOT_ALLOWED_MESSAGE) -> None:
        super().__init__(detail, code="mcp_tool_not_allowed", status_code=403)


class McpOperationError(AppException):
    """Catch-all controlled error for any other MCP protocol-level failure
    (an ``McpError`` that is not specifically a timeout) — never an
    unhandled 500."""

    def __init__(self, detail: str = _OPERATION_MESSAGE) -> None:
        super().__init__(detail, code="mcp_operation_error", status_code=502)
