from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from functools import partial

from fastapi import APIRouter, Header, Query
from fastapi import Request as FastAPIRequest
from fastapi.responses import JSONResponse, PlainTextResponse

from backend.config import Settings
from backend.errors import ServiceError
from backend.models import (
    EngineType,
    HealthResponse,
    PredictRequest,
    PredictResponse,
    TickerItem,
    TickerSearchResponse,
    TopAssetsResponse,
)
from backend.runtime import BlockingTaskRunner
from backend.services.cache import CacheBackend
from backend.services.market_data import resolve_top_assets
from backend.services.metrics import PredictionMetrics
from backend.services.prediction import build_prediction_response
from backend.services.rate_limit import RateLimiter
from backend.ticker_catalog import AssetType, search_tickers

router = APIRouter()


def _check_metrics_token(request: FastAPIRequest, authorization: str | None) -> None:
    """Reject metrics requests when METRICS_TOKEN is configured and not provided."""
    token = _settings(request).metrics_token
    if not token:
        return
    expected = f"Bearer {token}"
    if authorization != expected:
        raise ServiceError(
            status_code=403, code="forbidden", message="Invalid or missing metrics token."
        )


def _settings(request: FastAPIRequest) -> Settings:
    return request.app.state.settings


def _cache_backend(request: FastAPIRequest) -> CacheBackend:
    return request.app.state.cache_backend


def _rate_limiter(request: FastAPIRequest) -> RateLimiter:
    return request.app.state.rate_limiter


def _metrics(request: FastAPIRequest) -> PredictionMetrics:
    return request.app.state.metrics


def _blocking_runner(request: FastAPIRequest) -> BlockingTaskRunner:
    return request.app.state.blocking_runner


async def _predict_impl(request: FastAPIRequest, payload: PredictRequest) -> PredictResponse:
    _rate_limiter(request).enforce_predict_limit(request=request, engine=payload.engine)
    response = await build_prediction_response(
        payload,
        settings=_settings(request),
        cache_backend=_cache_backend(request),
        metrics=_metrics(request),
        blocking_runner=_blocking_runner(request),
        request_id=getattr(request.state, "request_id", None),
    )
    # Store latest evaluation for the validation-summary endpoint
    request.app.state.latest_evaluation = {
        "symbol": response.symbol,
        "engine_used": response.engine_used,
        "evaluation": response.evaluation.model_dump() if response.evaluation else None,
        "generated_at": response.generated_at,
    }
    return response


@router.get("/api/health", response_model=HealthResponse)
def health(request: FastAPIRequest) -> HealthResponse:
    cache = _cache_backend(request)
    uptime = int(time.monotonic() - request.app.state.boot_time)

    # Check Redis connectivity
    redis_status = "not_configured"
    if cache._redis is not None:
        try:
            cache._redis.ping()
            redis_status = "connected"
        except Exception:
            redis_status = "unavailable"

    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
        redis=redis_status,
        cache_size=cache.memory_size,
        uptime_seconds=uptime,
    )


@router.get("/api/health/ready")
async def health_ready(request: FastAPIRequest) -> JSONResponse:
    """Readiness probe — validates all dependencies are reachable."""
    checks: dict[str, str] = {}
    ready = True

    # Redis check
    cache = _cache_backend(request)
    try:
        if hasattr(cache, "_redis") and cache._redis is not None:
            await asyncio.get_event_loop().run_in_executor(None, cache._redis.ping)
            checks["redis"] = "connected"
        else:
            checks["redis"] = "not_configured"
    except Exception:
        checks["redis"] = "unavailable"
        ready = False

    # Market data provider check
    try:
        import yfinance  # noqa: F401

        checks["market_data"] = "available"
    except Exception:
        checks["market_data"] = "unavailable"

    status_code = 200 if ready else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "ready": ready,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
        },
    )


@router.get("/api/metrics")
def metrics(request: FastAPIRequest, authorization: str | None = Header(None)) -> dict:
    _check_metrics_token(request, authorization)
    return _metrics(request).snapshot()


@router.get("/api/metrics/prometheus")
def metrics_prometheus(
    request: FastAPIRequest, authorization: str | None = Header(None)
) -> PlainTextResponse:
    _check_metrics_token(request, authorization)
    cache = _cache_backend(request)
    uptime = int(time.monotonic() - request.app.state.boot_time)
    body = _metrics(request).prometheus_exposition(
        uptime_seconds=uptime,
        cache_size=cache.memory_size,
    )
    return PlainTextResponse(content=body, media_type="text/plain; charset=utf-8")


@router.get("/api/tickers", response_model=TickerSearchResponse)
def ticker_search(
    request: FastAPIRequest,
    query: str = Query("", max_length=30, description="Search text, e.g. K, KB, BTC"),
    limit: int = Query(20, ge=1, le=50),
    asset_type: AssetType = Query("stock", description="stock or crypto"),
) -> TickerSearchResponse:
    _rate_limiter(request).enforce_search_limit(request=request)
    tickers = [
        TickerItem.model_validate(item)
        for item in search_tickers(query=query, limit=limit, asset_type=asset_type)
    ]
    return TickerSearchResponse(
        query=query,
        asset_type=asset_type,
        tickers=tickers,
    )


@router.get("/api/top-assets", response_model=TopAssetsResponse)
@router.get("/api/top-stocks", response_model=TopAssetsResponse, include_in_schema=False)
async def top_assets(
    request: FastAPIRequest,
    limit: int = Query(10, ge=5, le=25),
    asset_type: AssetType = Query("stock", description="stock or crypto"),
) -> TopAssetsResponse:
    try:
        items, source = await _blocking_runner(request).run(
            partial(
                resolve_top_assets,
                limit=limit,
                asset_type=asset_type,
                cache_backend=_cache_backend(request),
                settings=_settings(request),
            ),
            timeout_seconds=_settings(request).top_assets_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise ServiceError(
            status_code=504,
            code="top_assets_timeout",
            message="Top assets lookup timed out.",
            retryable=True,
        ) from exc
    typed_items = [TickerItem.model_validate(item) for item in items]
    return TopAssetsResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        asset_type=asset_type,
        source=source,
        items=typed_items,
    )


@router.get("/api/predict", response_model=PredictResponse, include_in_schema=False)
async def predict_get(
    request: FastAPIRequest,
    symbol: str = Query(
        ..., min_length=1, max_length=20, description="Ticker symbol, e.g. AAPL or BTC"
    ),
    horizon: int = Query(30, ge=7, le=45, description="Days to forecast"),
    engine: EngineType = Query("ml", description="Prediction engine"),
    asset_type: AssetType = Query("stock", description="stock or crypto"),
    display_currency: str = Query("USD", description="Currency for displayed prices"),
) -> PredictResponse:
    return await _predict_impl(
        request,
        PredictRequest(
            symbol=symbol,
            horizon=horizon,
            engine=engine,
            asset_type=asset_type,
            display_currency=display_currency,
        ),
    )


@router.post("/api/predict", response_model=PredictResponse)
async def predict_post(request: FastAPIRequest, payload: PredictRequest) -> PredictResponse:
    return await _predict_impl(request, payload)


@router.get("/api/validation-summary")
def validation_summary(request: FastAPIRequest, authorization: str | None = Header(None)) -> dict:
    """Return configured ML quality-gate thresholds and the latest prediction evaluation."""
    _check_metrics_token(request, authorization)
    settings = _settings(request)
    latest = getattr(request.app.state, "latest_evaluation", None)
    return {
        "quality_gates": {
            "ml_min_validation_windows": settings.ml_min_validation_windows,
            "ml_min_directional_accuracy": settings.ml_min_directional_accuracy,
            "ml_max_mape_vs_baseline": settings.ml_max_mape_vs_baseline,
        },
        "latest_evaluation": latest,
    }
