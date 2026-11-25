"""Structured API error types and FastAPI exception handlers."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def format_error_payload(
    code: str,
    message: str,
    request_id: str,
    details: Optional[Any] = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details,
        "request_id": request_id,
    }


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_payload(
            code=exc.code,
            message=exc.message,
            details=exc.details,
            request_id=_request_id(request),
        ),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_payload(
            code=f"HTTP_{exc.status_code}",
            message=str(exc.detail),
            details=None,
            request_id=_request_id(request),
        ),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=format_error_payload(
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            details=exc.errors(),
            request_id=_request_id(request),
        ),
    )
