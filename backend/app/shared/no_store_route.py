"""Opt-in no-store responses, including dependency and validation failures."""
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.shared.exceptions import AppException


class NoStoreRoute(APIRoute):
    """Keep exception policy local; never reflect validation inputs."""

    error_detail = 'No se pudo completar la solicitud.'

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def no_store(request: Request):
            try:
                response = await handler(request)
            except (AppException, StarletteHTTPException) as error:
                error.headers = {**(error.headers or {}), 'Cache-Control': 'no-store'}
                raise
            except RequestValidationError:
                raise AppException(self.error_detail, 'validation_error', 422,
                                   headers={'Cache-Control': 'no-store'}) from None
            except Exception:
                raise AppException(self.error_detail, 'internal_error', 500,
                                   headers={'Cache-Control': 'no-store'}) from None
            response.headers['Cache-Control'] = 'no-store'
            return response

        return no_store
