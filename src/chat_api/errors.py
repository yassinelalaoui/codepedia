from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from chat import LocalDependencyUnavailableError

from .schemas import ApiErrorResponse
from .session_store import SessionNotFoundError


def _local_dependency_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    body = ApiErrorResponse(code="local_dependency_unavailable", message=str(exc))
    return JSONResponse(status_code=503, content=body.model_dump())


def _session_not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    body = ApiErrorResponse(code="session_not_found", message=str(exc))
    return JSONResponse(status_code=404, content=body.model_dump())


def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    message = "question must not be empty"
    if isinstance(exc, RequestValidationError):
        errors = exc.errors()
        if errors:
            message = str(errors[0].get("msg", message))
    body = ApiErrorResponse(code="empty_question", message=message)
    return JSONResponse(status_code=422, content=body.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(LocalDependencyUnavailableError, _local_dependency_unavailable_handler)
    app.add_exception_handler(SessionNotFoundError, _session_not_found_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
