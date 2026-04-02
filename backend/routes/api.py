from __future__ import annotations

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Query, Request as FastAPIRequest

from backend.config import Settings
from backend.errors import ServiceError
from backend.models import (
    EngineType,
    HealthResponse,
    PredictRequest,
    PredictResponse,
    PredictionSource,
    TickerSearchResponse,
    TopAssetsResponse,
)
from backend.services.ai import build_ai_forecast
from backend.services.cache import CacheBackend
from backend.services.forecast import build_prediction_summary, build_stat_forecast
from backend.services.ml_prediction import build_ml_prediction
from backend.services.market_data import (
    fetch_market_history,
    fetch_close_prices,
    normalize_symbol_input,
    resolve_top_assets,
)
from backend.services.rate_limit import RateLimiter
from backend.ticker_catalog import AssetType, search_tickers

logger = logging.getLogger("stock_predictor.api")

router = APIRouter()


def _settings(request: FastAPIRequest) -> Settings:
    return request.app.state.settings


def _cache_backend(request: FastAPIRequest) -> CacheBackend:
    return request.app.state.cache_backend


def _rate_limiter(request: FastAPIRequest) -> RateLimiter:
    return request.app.state.rate_limiter


def _predict_impl(request: FastAPIRequest, payload: PredictRequest) -> PredictResponse:
    settings = _settings(request)
    _rate_limiter(request).enforce_predict_limit(request=request, engine=payload.engine)

    ticker = normalize_symbol_input(payload.symbol)
    market_series = fetch_close_prices(
        symbol=ticker,
        asset_type=payload.asset_type,
        cache_backend=_cache_backend(request),
        settings=settings,
    )
    history, stat_forecast, stats = build_stat_forecast(
        market_series.close,
        payload.horizon,
        asset_type=payload.asset_type,
    )

    engine_used = "stat"
    model_name = "Statistical trend"
    engine_note = "Statistische trend op historische koersdata."
    forecast = stat_forecast
    source = PredictionSource(market_data=market_series.source, forecast="stat")
    degraded = False
    degradation_reason = None
    summary = build_prediction_summary(stat_forecast, last_close=stats["last_close"])
    evaluation = None
    model_version = None

    if payload.engine == "ml":
        try:
            market_history = fetch_market_history(
                symbol=ticker,
                asset_type=payload.asset_type,
                cache_backend=_cache_backend(request),
                settings=settings,
            )
            ml_result = build_ml_prediction(
                market_history,
                symbol=market_history.resolved_symbol,
                asset_type=payload.asset_type,
                horizon=payload.horizon,
                settings=settings,
            )
            history = ml_result.history
            forecast = ml_result.forecast
            stats = ml_result.stats
            summary = ml_result.summary
            evaluation = ml_result.evaluation
            model_version = ml_result.model_version
            engine_used = "ml"
            model_name = ml_result.model_name
            engine_note = ml_result.engine_note
            source = PredictionSource(market_data=market_history.source, forecast=ml_result.forecast_source)
        except (ServiceError, ValueError) as exc:
            error_message = exc.message if isinstance(exc, ServiceError) else str(exc)
            logger.warning(
                "ML forecast degraded to statistical fallback for symbol=%s: %s",
                market_series.resolved_symbol,
                error_message,
            )
            engine_used = "stat_fallback"
            model_name = "Statistical fallback"
            engine_note = f"ML-engine niet beschikbaar ({error_message}). Teruggevallen op statistische forecast."
            degraded = True
            degradation_reason = error_message
            source = PredictionSource(market_data=market_series.source, forecast="stat_fallback")

    elif payload.engine == "ai":
        try:
            forecast, ai_model = build_ai_forecast(
                market_series.resolved_symbol,
                market_series.close,
                payload.horizon,
                asset_type=payload.asset_type,
                settings=settings,
            )
            engine_used = "ai"
            model_name = ai_model["model"]
            engine_note = f"AI forecast via {ai_model['provider']} ({ai_model['model']})."
            source = PredictionSource(market_data=market_series.source, forecast=ai_model["source"])
            summary = build_prediction_summary(forecast, last_close=stats["last_close"])
        except ServiceError as exc:
            logger.warning(
                "AI forecast degraded to statistical fallback for symbol=%s: %s",
                market_series.resolved_symbol,
                exc.message,
            )
            engine_used = "stat_fallback"
            model_name = "Statistical fallback"
            engine_note = f"AI niet beschikbaar ({exc.message}). Teruggevallen op statistische forecast."
            degraded = True
            degradation_reason = exc.message
            source = PredictionSource(market_data=market_series.source, forecast="stat_fallback")

    return PredictResponse(
        symbol=market_series.resolved_symbol,
        requested_symbol=ticker,
        asset_type=payload.asset_type,
        currency=market_series.currency,
        generated_at=datetime.now(timezone.utc).isoformat(),
        horizon_days=payload.horizon,
        engine_requested=payload.engine,
        engine_used=engine_used,
        model_name=model_name,
        engine_note=engine_note,
        source=source,
        degraded=degraded,
        degradation_reason=degradation_reason,
        history=history,
        forecast=forecast,
        stats=stats,
        summary=summary,
        evaluation=evaluation,
        model_version=model_version,
        disclaimer="Dit is een probabilistische ML/statistische schatting en geen financieel advies.",
    )


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.now(timezone.utc).isoformat())


@router.get("/api/tickers", response_model=TickerSearchResponse)
def ticker_search(
    query: str = Query("", max_length=30, description="Zoektekst, bv K, KB, BTC"),
    limit: int = Query(20, ge=1, le=50),
    asset_type: AssetType = Query("stock", description="stock of crypto"),
) -> TickerSearchResponse:
    return TickerSearchResponse(
        query=query,
        asset_type=asset_type,
        tickers=search_tickers(query=query, limit=limit, asset_type=asset_type),
    )


@router.get("/api/top-assets", response_model=TopAssetsResponse)
@router.get("/api/top-stocks", response_model=TopAssetsResponse, include_in_schema=False)
def top_assets(
    request: FastAPIRequest,
    limit: int = Query(10, ge=5, le=25),
    asset_type: AssetType = Query("stock", description="stock of crypto"),
) -> TopAssetsResponse:
    items, source = resolve_top_assets(
        limit=limit,
        asset_type=asset_type,
        cache_backend=_cache_backend(request),
        settings=_settings(request),
    )
    return TopAssetsResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        asset_type=asset_type,
        source=source,
        items=items,
    )


@router.get("/api/predict", response_model=PredictResponse, include_in_schema=False)
def predict_get(
    request: FastAPIRequest,
    symbol: str = Query(..., min_length=1, max_length=20, description="Ticker symbool, bv AAPL of BTC"),
    horizon: int = Query(30, ge=7, le=45, description="Aantal dagen om te voorspellen"),
    engine: EngineType = Query("stat", description="Voorspellingsengine"),
    asset_type: AssetType = Query("stock", description="stock of crypto"),
) -> PredictResponse:
    return _predict_impl(
        request,
        PredictRequest(symbol=symbol, horizon=horizon, engine=engine, asset_type=asset_type),
    )


@router.post("/api/predict", response_model=PredictResponse)
def predict_post(request: FastAPIRequest, payload: PredictRequest) -> PredictResponse:
    return _predict_impl(request, payload)
