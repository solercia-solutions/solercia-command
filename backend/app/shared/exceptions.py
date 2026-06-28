"""Application exception type and FastAPI exception handlers.

All error responses share the same envelope ``{detail, code, status}`` with
user-facing messages written in Colombian formal Spanish (tuteo).
"""

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppException(Exception):
    """Domain error carrying an HTTP status, a stable code and a message."""

    def __init__(
        self,
        detail: str,
        code: str = "app_error",
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        self.detail = detail
        self.code = code
        self.status_code = status_code
        super().__init__(detail)


def register_exception_handlers(app: FastAPI) -> None:
    """Register handlers that normalize every error into the shared envelope."""

    @app.exception_handler(AppException)
    async def _handle_app_exception(
        request: Request, exc: AppException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "code": exc.code,
                "status": exc.status_code,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Ocurrió un error."
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": detail,
                "code": "http_error",
                "status": exc.status_code,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Los datos enviados no son válidos.",
                "code": "validation_error",
                "status": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "errors": jsonable_encoder(exc.errors()),
            },
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Ocurrió un error inesperado. Inténtalo de nuevo.",
                "code": "internal_error",
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            },
        )
