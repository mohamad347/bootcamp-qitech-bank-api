import logging
import time

from fastapi import FastAPI, Request

from constants import BYPASS_ENDPOINTS
from utils.logger import get_logger


logger = get_logger(__name__)


def _route_template(request: Request):
    route = request.scope.get("route")
    return getattr(route, "path", None)


def _exception_type(exception: Exception) -> str:
    while isinstance(exception, BaseExceptionGroup) and len(exception.exceptions) == 1:
        exception = exception.exceptions[0]
    return type(exception).__name__


def register_request_logger_middleware(application: FastAPI) -> None:
    """Emit one start event and exactly one terminal event per request."""

    @application.middleware("http")
    async def log_request(request: Request, call_next):
        lifecycle_level = logging.DEBUG if request.url.path in BYPASS_ENDPOINTS else logging.INFO
        started_at = time.perf_counter()
        logger.log(
            lifecycle_level,
            "request.started",
            extra={"event": "request.started", "method": request.method},
        )

        try:
            response = await call_next(request)
        except Exception as exception:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
            logger.error(
                "request.failed",
                exc_info=True,
                extra={
                    "event": "request.failed",
                    "method": request.method,
                    "route": _route_template(request),
                    "status_code": 500,
                    "duration_ms": elapsed_ms,
                    "exception_type": _exception_type(exception),
                },
            )
            raise

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
        status_code = response.status_code
        route = _route_template(request)

        if status_code < 400:
            logger.log(
                lifecycle_level,
                "request.finished",
                extra={
                    "event": "request.finished",
                    "method": request.method,
                    "route": route,
                    "status_code": status_code,
                    "duration_ms": elapsed_ms,
                },
            )
        else:
            level = logging.WARNING if status_code == 403 else logging.INFO
            logger.log(
                level,
                "request.rejected",
                extra={
                    "event": "request.rejected",
                    "method": request.method,
                    "route": route,
                    "status_code": status_code,
                    "error_code": getattr(request.state, "error_code", None),
                    "duration_ms": elapsed_ms,
                },
            )

        return response
