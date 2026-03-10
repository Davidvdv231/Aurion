from __future__ import annotations

from pathlib import Path
import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

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


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_title, version=settings.version)

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
                "message": "Request payload is ongeldig.",
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
                "message": "Interne serverfout.",
                "retryable": False,
            }
        )
        return JSONResponse(status_code=500, content=jsonable_encoder(envelope))

    app.include_router(api_router)

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    return app


app = create_app()
