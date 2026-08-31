from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from chat import LocalDependencyUnavailableError

from .schemas import ApiErrorResponse
from .security import UnauthorizedError
from .session_store import SessionNotFoundError


def _local_dependency_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    body = ApiErrorResponse(code="local_dependency_unavailable", message=str(exc))
    return JSONResponse(status_code=503, content=body.model_dump())


def _session_not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    body = ApiErrorResponse(code="session_not_found", message=str(exc))
    return JSONResponse(status_code=404, content=body.model_dump())


def _unauthorized_handler(request: Request, exc: Exception) -> JSONResponse:
    body = ApiErrorResponse(code="unauthorized", message=str(exc))
    return JSONResponse(status_code=401, content=body.model_dump())


def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    message = "question must not be empty"
    code = "empty_question"
    if isinstance(exc, RequestValidationError):
        errors = exc.errors()
        if errors:
            first = errors[0]
            message = str(first.get("msg", message))
            # `empty_question` is the code the chat client keys on, and it was
            # being returned for *every* validation failure - an out-of-range
            # `limit` on the failover log included. Only the question field
            # earns it.
            if "question" not in tuple(first.get("loc", ())):
                code = "invalid_request"
    body = ApiErrorResponse(code=code, message=message)
    return JSONResponse(status_code=422, content=body.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(LocalDependencyUnavailableError, _local_dependency_unavailable_handler)
    app.add_exception_handler(SessionNotFoundError, _session_not_found_handler)
    app.add_exception_handler(UnauthorizedError, _unauthorized_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
