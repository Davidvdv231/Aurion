from __future__ import annotations

from pathlib import Path
import logging

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
from backend.errors import ErrorEnvelope, ServiceError
from backend.routes import router as api_router
from backend.services.cache import CacheBackend
from backend.services.rate_limit import RateLimiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("stock_predictor.app")

# Maximum request body size (1 MB)
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
    """Add security headers to all responses."""

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

        # Cache-Control for static assets
        path = request.url.path
        if path.startswith("/vendor/") or path.startswith("/icons/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.endswith((".css", ".js", ".webmanifest")):
            response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
        elif path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"

        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject request bodies exceeding the size limit."""

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "payload_too_large",
                        "message": f"Request body exceeds {MAX_REQUEST_BODY_BYTES // 1024}KB limit.",
                        "retryable": False,
                    }
                },
            )
        return await call_next(request)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_title, version=settings.version)

    # Middleware stack (order matters: outermost first)
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allow_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.cache_backend = CacheBackend(settings)
    app.state.rate_limiter = RateLimiter(settings)

    @app.exception_handler(ServiceError)
    async def handle_service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(exc.to_envelope()))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        envelope = ErrorEnvelope(
            error={
                "code": "invalid_request",
                "message": "Invalid request payload.",
                "details": {"issues": _normalized_validation_issues(exc)},
            }
        )
        return JSONResponse(status_code=422, content=jsonable_encoder(envelope))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled application error", exc_info=exc)
        envelope = ErrorEnvelope(
            error={
                "code": "internal_error",
                "message": "Internal server error.",
                "retryable": False,
            }
        )
        return JSONResponse(status_code=500, content=jsonable_encoder(envelope))

    app.include_router(api_router)

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    return app


app = create_app()
