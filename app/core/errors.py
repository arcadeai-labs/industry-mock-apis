"""Uniform error envelope: {"error": {"code", "message", "details"}, "request_id"}."""
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


def not_found(entity: str, ident: Any) -> ApiError:
    return ApiError(404, "not_found", f"{entity} '{ident}' was not found.")


def bad_request(message: str, details: Any = None) -> ApiError:
    return ApiError(400, "bad_request", message, details)


def conflict(code: str, message: str, details: Any = None) -> ApiError:
    return ApiError(409, code, message, details)


def forbidden(code: str, message: str, details: Any = None) -> ApiError:
    return ApiError(403, code, message, details)


def error_body(request: Request, code: str, message: str, details: Any = None) -> dict:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    body["request_id"] = request.scope.get("request_id")
    return jsonable_encoder(body)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse(
            error_body(request, exc.code, exc.message, exc.details),
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            error_body(request, "validation_error", "Request failed validation.", exc.errors()),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(
            error_body(request, code, str(exc.detail)),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )
