import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings
from app.logger import get_logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.logger = get_logger(__name__)

    async def dispatch(self, request: Request, call_next):
        started_at = time.perf_counter()
        self.logger.info("Request started: %s %s", request.method, request.url.path)

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started_at) * 1000
            self.logger.exception(
                "Request failed: %s %s completed_in=%.2fms",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - started_at) * 1000
        status_code = response.status_code
        log_message = "Request completed: %s %s status=%s completed_in=%.2fms"
        log_args = (request.method, request.url.path, status_code, duration_ms)

        if status_code >= 500:
            self.logger.error(log_message, *log_args)
        elif status_code >= 400:
            self.logger.warning(log_message, *log_args)
        elif settings.DEBUG:
            self.logger.debug(log_message, *log_args)
        else:
            self.logger.info(log_message, *log_args)

        return response
