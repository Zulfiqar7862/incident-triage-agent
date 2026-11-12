"""Map application exceptions to HTTP responses with an operator-facing projection."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.application.exceptions import ConcurrencyConflict, InvalidInput, NotFound, RunStateError, TooBusy
from app.presentation.operator import error_display

STATUS_BY_ERROR: dict[type[Exception], int] = {
    NotFound: 404,
    RunStateError: 409,
    InvalidInput: 422,
    TooBusy: 429,
    ConcurrencyConflict: 409,
}


def install_error_handlers(app: FastAPI) -> None:
    for exc_type, status in STATUS_BY_ERROR.items():

        async def handler(_: Request, exc: Exception, status: int = status) -> JSONResponse:
            headers = {"Retry-After": "30"} if status == 429 else None
            return JSONResponse(
                {"detail": str(exc), "operator": error_display(status)}, status_code=status, headers=headers
            )

        app.add_exception_handler(exc_type, handler)
