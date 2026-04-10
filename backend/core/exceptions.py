"""
Custom exceptions and FastAPI exception handlers.

All application errors inherit from :class:`AppError`, which carries an
HTTP status code. :func:`register_exception_handlers` attaches a single
FastAPI handler that turns any :class:`AppError` subclass into a JSON
response with the matching status code.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

__all__ = [
    "AppError",
    "AuthenticationError",
    "ConflictError",
    "NotFoundError",
    "PermissionDeniedError",
    "ValidationError",
    "register_exception_handlers",
]


class AppError(Exception):
    """Base application error with an HTTP status code."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, resource: str, identifier: str | int) -> None:
        super().__init__(f"{resource} '{identifier}' not found", status_code=404)


class ConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=409)


class AuthenticationError(AppError):
    def __init__(self, message: str = "Invalid or missing API key") -> None:
        super().__init__(message, status_code=401)


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message, status_code=403)


class ValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach custom exception handlers to the FastAPI app."""

    @app.exception_handler(AppError)
    async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message},
        )
