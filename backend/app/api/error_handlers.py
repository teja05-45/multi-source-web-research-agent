"""Consistent API error contract and global exception handlers.

Every failure returned to a client uses the same envelope::

    {
        "error": {
            "code": "provider_unavailable",
            "message": "Search provider temporarily unavailable.",
            "request_id": "abc123",
            "retryable": true
        }
    }

Stack traces are never exposed to clients; they are logged server-side with
the same ``request_id`` for correlation.

A note on CORS: the ``Exception`` handler is installed on Starlette's
outermost ``ServerErrorMiddleware``, which runs *outside* ``CORSMiddleware``.
Without help, an unhandled 500 would therefore be delivered without CORS
headers, and the browser would mask it as an opaque ``TypeError: Failed to
fetch``. To keep failures observable, this module explicitly echoes the
request ``Origin`` when it is allowed.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.models.errors import ErrorCode, ResearchAgentError
from app.observability.logging import get_request_id

logger = logging.getLogger("research_agent.api.errors")

# Domain error code -> (HTTP status, retryable)
_CODE_MAP: dict[ErrorCode, tuple[int, bool]] = {
    ErrorCode.VALIDATION_ERROR: (400, False),
    ErrorCode.PROVIDER_ERROR: (502, True),
    ErrorCode.ALL_PROVIDERS_FAILED: (502, True),
    ErrorCode.FETCH_ERROR: (502, True),
    ErrorCode.LLM_ERROR: (502, True),
    ErrorCode.INSUFFICIENT_EVIDENCE: (422, False),
    ErrorCode.INTERNAL_ERROR: (500, False),
}


def _cors_headers_for(request: Request) -> dict[str, str]:
    """Echo the request Origin when it is in the configured allow-list."""
    origin = request.headers.get("origin")
    if not origin:
        return {}
    allowed = get_settings().cors_origins_list
    if origin in allowed or "*" in allowed:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }
    return {}


def error_json(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    retryable: bool,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a JSON error response in the standard envelope."""
    merged_headers = {"X-Request-ID": request_id or get_request_id()}
    merged_headers.update(_cors_headers_for(request))
    if headers:
        merged_headers.update(headers)
    return JSONResponse(
        status_code=status_code,
        headers=merged_headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id or get_request_id(),
                "retryable": retryable,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers that guarantee the error contract for every failure."""

    @app.exception_handler(ResearchAgentError)
    async def _domain_error(request: Request, exc: ResearchAgentError) -> JSONResponse:
        status_code, retryable = _CODE_MAP.get(exc.code, (500, False))
        logger.warning(
            "domain_error",
            extra={"error_code": exc.code.value, "error_message": exc.message},
        )
        return error_json(
            request,
            status_code=status_code,
            code=exc.code.value,
            message=exc.message,
            retryable=retryable,
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Surface the first validation problem without leaking internals.
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        detail = first.get("msg", "Invalid request.")
        message = f"Invalid request: {loc} {detail}".strip()
        return error_json(
            request,
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR.value,
            message=message,
            retryable=False,
        )

    @app.exception_handler(ResponseValidationError)
    async def _response_validation(request: Request, exc: ResponseValidationError) -> JSONResponse:
        # A response-model mismatch is a server bug. Log loudly, tell the
        # client nothing that could be misconstrued as a data problem.
        logger.error("response_validation_error", exc_info=exc)
        return error_json(
            request,
            status_code=500,
            code=ErrorCode.INTERNAL_ERROR.value,
            message="The research backend produced a response it could not serialize.",
            retryable=True,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error_code" in exc.detail:
            code = str(exc.detail["error_code"])
            message = str(exc.detail.get("message", "Request failed."))
        elif exc.status_code == 404:
            code = "not_found"
            message = "Resource not found."
        elif exc.status_code == 405:
            code = "method_not_allowed"
            message = "Method not allowed."
        else:
            code = "http_error"
            message = str(exc.detail)
        return error_json(
            request,
            status_code=exc.status_code,
            code=code,
            message=message,
            retryable=exc.status_code >= 500,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Never leak stack traces; correlate via request_id in the logs.
        logger.exception("unhandled_exception")
        return error_json(
            request,
            status_code=500,
            code=ErrorCode.INTERNAL_ERROR.value,
            message="An unexpected error occurred while processing this request.",
            retryable=True,
        )
