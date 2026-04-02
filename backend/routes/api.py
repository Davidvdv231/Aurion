from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from functools import partial

from fastapi import APIRouter, Query, Request as FastAPIRequest

from backend.config import Settings
from backend.errors import ServiceError
from backend.models import (
    EngineType,
    HealthResponse,
    PredictRequest,
    PredictResponse,
    PredictionEvaluation,
    PredictionSource,
    PredictionSummary,
    TickerSearchResponse,
    TopAssetsResponse,
)
from backend.services.ai import build_ai_forecast
from backend.services.cache import CacheBackend
from backend.services.forecast import build_stat_forecast
from backend.services.market_data import (
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


def _build_summary(
    forecast: list[dict],
    stats: dict,
    evaluation: PredictionEvaluation | None = None,
) -> PredictionSummary:
    """Build a prediction summary with signal from forecast data."""
    if not forecast:
        return PredictionSummary(
            expected_price=stats["last_close"],
            expected_return_pct=0.0,
            trend="neutral",
            confidence_score=0.5,
            probability_up=0.5,
            signal="hold",
        )

    last_close = stats["last_close"]
    final_predicted = forecast[-1]["predicted"]
    expected_return = ((final_predicted / last_close) - 1.0) * 100 if last_close > 0 else 0.0

    # Trend classification
    if expected_return > 2.0:
        trend = "bullish"
    elif expected_return < -2.0:
        trend = "bearish"
    else:
        trend = "neutral"

    # Probability up: fraction of forecast points above last close
    up_count = sum(1 for pt in forecast if pt["predicted"] > last_close)
    probability_up = up_count / len(forecast) if forecast else 0.5

    # Confidence score based on band width and evaluation metrics
    avg_band_width = 0.0
    if forecast:
        widths = [(pt["upper"] - pt["lower"]) / max(pt["predicted"], 0.01) for pt in forecast]
        avg_band_width = sum(widths) / len(widths)

    # Narrower bands = higher confidence (inverted, clamped 0.3-0.95)
    band_confidence = max(0.3, min(0.95, 1.0 - avg_band_width * 2))

    # Boost confidence if we have good directional accuracy
    if evaluation and evaluation.directional_accuracy is not None:
        confidence_score = 0.6 * band_confidence + 0.4 * evaluation.directional_accuracy
    else:
        confidence_score = band_confidence * 0.85

    confidence_score = round(max(0.0, min(1.0, confidence_score)), 2)

    # Signal generation
    if expected_return > 5.0 and confidence_score > 0.65:
        signal = "strong_buy"
    elif expected_return > 1.5 and confidence_score > 0.5:
        signal = "buy"
    elif expected_return < -5.0 and confidence_score > 0.65:
        signal = "strong_sell"
    elif expected_return < -1.5 and confidence_score > 0.5:
        signal = "sell"
    else:
        signal = "hold"

    return PredictionSummary(
        expected_price=round(final_predicted, 2),
        expected_return_pct=round(expected_return, 2),
        trend=trend,
        confidence_score=confidence_score,
        probability_up=round(probability_up, 2),
        signal=signal,
    )


async def _predict_impl(request: FastAPIRequest, payload: PredictRequest) -> PredictResponse:
    settings = _settings(request)
    _rate_limiter(request).enforce_predict_limit(request=request, engine=payload.engine)

    ticker = normalize_symbol_input(payload.symbol)

    loop = asyncio.get_running_loop()
    market_series = await loop.run_in_executor(
        None,
        partial(
            fetch_close_prices,
            symbol=ticker,
            asset_type=payload.asset_type,
            cache_backend=_cache_backend(request),
            settings=settings,
        ),
    )

    history, stat_forecast, stats = build_stat_forecast(
        market_series.close,
        payload.horizon,
        asset_type=payload.asset_type,
    )

    engine_used = "stat"
    model_name = "Statistical Trend"
    engine_note = "Log-linear statistical trend model on historical prices."
    forecast = stat_forecast
    source = PredictionSource(market_data=market_series.source, forecast="stat")
    degraded = False
    degradation_reason = None
    evaluation = None

    # --- ML Engine ---
    if payload.engine == "ml":
        try:
            from backend.ml.service import train_and_predict

            ml_result, ml_metrics = await loop.run_in_executor(
                None,
                partial(
                    train_and_predict,
                    symbol=market_series.resolved_symbol,
                    close=market_series.close,
                    horizon=payload.horizon,
                    asset_type=payload.asset_type,
                ),
            )

            forecast = [
                {
                    "date": ml_result.dates[i],
                    "predicted": round(float(ml_result.predicted[i]), 2),
                    "lower": round(float(ml_result.lower[i]), 2),
                    "upper": round(float(ml_result.upper[i]), 2),
                }
                for i in range(len(ml_result.dates))
            ]
            evaluation = PredictionEvaluation(
                mae=ml_metrics.mae,
                rmse=ml_metrics.rmse,
                mape=ml_metrics.mape,
                directional_accuracy=ml_metrics.directional_accuracy,
                validation_windows=ml_metrics.validation_windows,
            )
            engine_used = "ml"
            model_name = "Aurion Analog Forecaster"
            engine_note = (
                f"Pattern-matching ML model using {ml_result.neighbors_used} nearest historical analogs "
                f"with {len(market_series.close)} data points."
            )
            source = PredictionSource(market_data=market_series.source, forecast="ml_analog")

        except Exception as exc:
            logger.warning(
                "ML forecast failed for symbol=%s, falling back to stat: %s",
                market_series.resolved_symbol, exc,
            )
            engine_used = "stat_fallback"
            model_name = "Statistical Fallback"
            engine_note = f"ML engine unavailable ({exc}). Fell back to statistical forecast."
            degraded = True
            degradation_reason = str(exc)
            source = PredictionSource(market_data=market_series.source, forecast="stat_fallback")

    # --- AI Engine ---
    elif payload.engine == "ai":
        try:
            ai_forecast, ai_model = await loop.run_in_executor(
                None,
                partial(
                    build_ai_forecast,
                    symbol=market_series.resolved_symbol,
                    close=market_series.close,
                    horizon=payload.horizon,
                    asset_type=payload.asset_type,
                    settings=settings,
                ),
            )
            forecast = ai_forecast
            engine_used = "ai"
            model_name = ai_model["model"]
            engine_note = f"AI forecast via {ai_model['provider']} ({ai_model['model']})."
            source = PredictionSource(market_data=market_series.source, forecast=ai_model["source"])
        except ServiceError as exc:
            logger.warning(
                "AI forecast degraded to stat fallback for symbol=%s: %s",
                market_series.resolved_symbol, exc.message,
            )
            engine_used = "stat_fallback"
            model_name = "Statistical Fallback"
            engine_note = f"AI unavailable ({exc.message}). Fell back to statistical forecast."
            degraded = True
            degradation_reason = exc.message
            source = PredictionSource(market_data=market_series.source, forecast="stat_fallback")

    summary = _build_summary(forecast, stats, evaluation)

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
        disclaimer="This is a statistical/AI estimate and not financial advice. Past performance does not guarantee future results.",
    )


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.now(timezone.utc).isoformat())


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
