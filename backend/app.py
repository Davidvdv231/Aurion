from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from backend.config import get_settings
from backend.errors import ApiErrorPayload, ErrorEnvelope, ServiceError
from backend.routes import router as api_router
from backend.runtime import BlockingTaskRunner
from backend.services.cache import CacheBackend
from backend.services.metrics import PredictionMetrics
from backend.services.rate_limit import RateLimiter


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line for structured log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("prediction_"):
                entry[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


_handler = logging.StreamHandler()
_handler.setFormatter(_JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger("stock_predictor.app")

_BOOT_TIME = time.monotonic()
MAX_REQUEST_BODY_BYTES = 1_048_576


def _normalized_validation_issues(exc: RequestValidationError) -> list[dict]:
    issues: list[dict] = []
    for issue in exc.errors():
        normalized = dict(issue)
        context = normalized.get("ctx")
        if isinstance(context, dict):
            normalized["ctx"] = {
                key: str(value) if isinstance(value, Exception) else value
                for key, value in context.items()
            }
        issues.append(normalized)
    return issues


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )

        path = request.url.path
        if path.startswith("/vendor/") or path.startswith("/icons/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.endswith((".css", ".js", ".webmanifest")):
            response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
        elif path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"

        return response


def _payload_too_large_response(max_body_bytes: int) -> JSONResponse:
    limit_kb = max_body_bytes // 1024
    return JSONResponse(
        status_code=413,
        content={
            "error": {
                "code": "payload_too_large",
                "message": f"Request body exceeds {limit_kb}KB limit.",
                "retryable": False,
            }
        },
    )


class RequestSizeLimitMiddleware:
    def __init__(self, app, max_body_bytes: int = MAX_REQUEST_BODY_BYTES) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        content_length_raw = headers.get(b"content-length")
        if content_length_raw is not None:
            try:
                if int(content_length_raw.decode("latin-1")) > self.max_body_bytes:
                    response = _payload_too_large_response(self.max_body_bytes)
                    await response(scope, receive, send)
                    return
            except ValueError:
                pass

        # Buffer the request once so size checks do not depend on downstream body consumption.
        total_bytes = 0
        buffered_messages: list[dict] = []
        while True:
            message = await receive()
            buffered_messages.append(message)
            if message["type"] == "http.request":
                total_bytes += len(message.get("body", b"") or b"")
                if total_bytes > self.max_body_bytes:
                    response = _payload_too_large_response(self.max_body_bytes)
                    await response(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break
            else:
                break

        buffered_iter = iter(buffered_messages)

        async def buffered_receive():
            try:
                return next(buffered_iter)
            except StopIteration:
                return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, buffered_receive, send)


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.cache_backend = CacheBackend(settings)
        app.state.rate_limiter = RateLimiter(settings)
        app.state.metrics = PredictionMetrics()
        app.state.boot_time = _BOOT_TIME
        app.state.blocking_runner = BlockingTaskRunner(
            max_workers=settings.executor_max_workers,
            max_in_flight_calls=settings.executor_max_workers,
            thread_name_prefix="aurion",
        )
        try:
            yield
        finally:
            app.state.blocking_runner.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title=settings.app_title, version=settings.version, lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=MAX_REQUEST_BODY_BYTES)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allow_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(ServiceError)
    async def handle_service_error(_: Request, exc: ServiceError) -> JSONResponse:
        envelope = exc.to_envelope()
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(envelope),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        envelope = ErrorEnvelope(
            error=ApiErrorPayload(
                code="invalid_request",
                message="Invalid request payload.",
                details={"issues": _normalized_validation_issues(exc)},
            ),
        )
        return JSONResponse(status_code=422, content=jsonable_encoder(envelope))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled application error", exc_info=exc)
        envelope = ErrorEnvelope(
            error=ApiErrorPayload(
                code="internal_error",
                message="Internal server error.",
                retryable=False,
            ),
        )
        return JSONResponse(status_code=500, content=jsonable_encoder(envelope))

    app.include_router(api_router)

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    return app


app = create_app()
