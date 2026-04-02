from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from functools import partial

from fastapi import APIRouter, Query, Request as FastAPIRequest

from backend.config import Settings
from backend.models import (
    EngineType,
    HealthResponse,
    PredictRequest,
    PredictResponse,
    TickerSearchResponse,
    TopAssetsResponse,
)
from backend.services.cache import CacheBackend
from backend.services.market_data import (
    resolve_top_assets,
)
from backend.services.metrics import PredictionMetrics
from backend.services.prediction import build_prediction_response
from backend.services.rate_limit import RateLimiter
from backend.ticker_catalog import AssetType, search_tickers

router = APIRouter()


def _settings(request: FastAPIRequest) -> Settings:
    return request.app.state.settings


def _cache_backend(request: FastAPIRequest) -> CacheBackend:
    return request.app.state.cache_backend


def _rate_limiter(request: FastAPIRequest) -> RateLimiter:
    return request.app.state.rate_limiter


def _metrics(request: FastAPIRequest) -> PredictionMetrics:
    return request.app.state.metrics


async def _predict_impl(request: FastAPIRequest, payload: PredictRequest) -> PredictResponse:
    _rate_limiter(request).enforce_predict_limit(request=request, engine=payload.engine)
    return await build_prediction_response(
        payload,
        settings=_settings(request),
        cache_backend=_cache_backend(request),
        metrics=_metrics(request),
    )


@router.get("/api/health", response_model=HealthResponse)
def health(request: FastAPIRequest) -> HealthResponse:
    import time as _time
    from backend.app import _BOOT_TIME

    cache = _cache_backend(request)
    uptime = int(_time.monotonic() - _BOOT_TIME)

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
        cache_size=len(cache._memory._items),
        uptime_seconds=uptime,
    )


@router.get("/api/metrics")
def metrics(request: FastAPIRequest) -> dict:
    return _metrics(request).snapshot()


@router.get("/api/tickers", response_model=TickerSearchResponse)
def ticker_search(
    request: FastAPIRequest,
    query: str = Query("", max_length=30, description="Search text, e.g. K, KB, BTC"),
    limit: int = Query(20, ge=1, le=50),
    asset_type: AssetType = Query("stock", description="stock or crypto"),
) -> TickerSearchResponse:
    _rate_limiter(request).enforce_search_limit(request=request)
    return TickerSearchResponse(
        query=query,
        asset_type=asset_type,
        tickers=search_tickers(query=query, limit=limit, asset_type=asset_type),
    )


@router.get("/api/top-assets", response_model=TopAssetsResponse)
@router.get("/api/top-stocks", response_model=TopAssetsResponse, include_in_schema=False)
async def top_assets(
    request: FastAPIRequest,
    limit: int = Query(10, ge=5, le=25),
    asset_type: AssetType = Query("stock", description="stock or crypto"),
) -> TopAssetsResponse:
    loop = asyncio.get_running_loop()
    items, source = await loop.run_in_executor(
        None,
        partial(
            resolve_top_assets,
            limit=limit,
            asset_type=asset_type,
            cache_backend=_cache_backend(request),
            settings=_settings(request),
        ),
    )
    return TopAssetsResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        asset_type=asset_type,
        source=source,
        items=items,
    )


@router.get("/api/predict", response_model=PredictResponse, include_in_schema=False)
async def predict_get(
    request: FastAPIRequest,
    symbol: str = Query(..., min_length=1, max_length=20, description="Ticker symbol, e.g. AAPL or BTC"),
    horizon: int = Query(30, ge=7, le=45, description="Days to forecast"),
    engine: EngineType = Query("ml", description="Prediction engine"),
    asset_type: AssetType = Query("stock", description="stock or crypto"),
) -> PredictResponse:
    return await _predict_impl(
        request,
        PredictRequest(symbol=symbol, horizon=horizon, engine=engine, asset_type=asset_type),
    )


@router.post("/api/predict", response_model=PredictResponse)
async def predict_post(request: FastAPIRequest, payload: PredictRequest) -> PredictResponse:
    return await _predict_impl(request, payload)
