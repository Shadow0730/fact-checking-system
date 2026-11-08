"""API errors, always returned as {"error": {"code": ..., "message": ...}}."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.clients import SarvamBadRequest, SarvamUnavailable
from app.logging import get_logger

log = get_logger(__name__)


class AppError(Exception):
    def __init__(self, code: str, status: int, message: str):
        super().__init__(message)
        self.code, self.status, self.message = code, status, message


def _body(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app(_: Request, e: AppError):
        return _body(e.code, e.message, e.status)

    @app.exception_handler(SarvamUnavailable)
    async def _unavail(_: Request, e: SarvamUnavailable):
        return _body("SARVAM_UNAVAILABLE", str(e), 502)

    @app.exception_handler(SarvamBadRequest)
    async def _bad(_: Request, e: SarvamBadRequest):
        return _body("SARVAM_BAD_REQUEST", str(e), 500)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, e: RequestValidationError):
        return _body("INVALID_REQUEST", str(e.errors())[:1000], 422)

    # Catch-all as a middleware (not an exception_handler): FastAPI runs Exception handlers outside every
    # middleware, so the response would miss the CORS headers and the browser would report
    # "cannot reach the backend" instead of the real error. main.py adds CORS after this, i.e. outside it.
    @app.middleware("http")
    async def _other(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            log.exception("unhandled error")
            return _body("INTERNAL", f"{type(e).__name__}: {e}"[:500], 500)
