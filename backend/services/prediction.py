from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import math
from functools import partial

from backend.config import Settings
from backend.errors import ServiceError
from backend.models import (
    PredictRequest,
    PredictResponse,
    PredictionEvaluation,
    PredictionSource,
    PredictionSummary,
)
from backend.services.ai import build_ai_forecast
from backend.services.cache import CacheBackend
from backend.services.forecast import build_stat_forecast
from backend.services.market_data import fetch_close_prices, normalize_symbol_input

logger = logging.getLogger("stock_predictor.prediction")


def _log_prediction_event(level: int, event: str, **fields: object) -> None:
    clean_fields = {key: value for key, value in fields.items() if value is not None}
    details = " ".join(f"{key}={clean_fields[key]}" for key in sorted(clean_fields))
    message = event if not details else f"{event} {details}"
    logger.log(
        level,
        message,
        extra={
            "prediction_event": event,
            **{f"prediction_{key}": value for key, value in clean_fields.items()},
        },
    )


def _degradation_fields(
    *,
    degraded: bool,
    code: str | None = None,
    message: str | None = None,
) -> tuple[bool, str | None, str | None, str | None]:
    if not degraded:
        return False, None, None, None
    return True, code, message, message


def _build_summary(
    forecast: list[dict],
    stats: dict,
    evaluation: PredictionEvaluation | None = None,
) -> PredictionSummary:
    if not forecast:
        return PredictionSummary(
            expected_price=stats["last_close"],
            expected_return_pct=0.0,
            trend="neutral",
            confidence_tier="low",
            probability_up=0.5,
            signal="neutral",
        )

    last_close = stats["last_close"]
    final_predicted = forecast[-1]["predicted"]
    expected_return = ((final_predicted / last_close) - 1.0) * 100 if last_close > 0 else 0.0

    if expected_return > 2.0:
        trend = "bullish"
    elif expected_return < -2.0:
        trend = "bearish"
    else:
        trend = "neutral"

    final_upper = forecast[-1]["upper"]
    final_lower = forecast[-1]["lower"]
    band_std = (final_upper - final_lower) / (2 * 1.28) if final_upper > final_lower else 0.01
    z = (final_predicted - last_close) / max(band_std, 0.01)
    probability_up = 1.0 / (1.0 + math.exp(-1.7 * min(max(z, -10), 10)))

    widths = [(pt["upper"] - pt["lower"]) / max(pt["predicted"], 0.01) for pt in forecast]
    avg_band_width = sum(widths) / len(widths)
    band_confidence = max(0.0, min(1.0, 1.0 - avg_band_width * 2))

    if evaluation and evaluation.directional_accuracy is not None:
        raw_confidence = 0.6 * band_confidence + 0.4 * evaluation.directional_accuracy
    else:
        raw_confidence = band_confidence * 0.85

    if raw_confidence >= 0.65:
        confidence_tier = "high"
    elif raw_confidence >= 0.40:
        confidence_tier = "medium"
    else:
        confidence_tier = "low"

    if expected_return > 5.0 and confidence_tier == "high":
        signal = "bullish"
    elif expected_return > 1.5 and confidence_tier != "low":
        signal = "mildly_bullish"
    elif expected_return < -5.0 and confidence_tier == "high":
        signal = "bearish"
    elif expected_return < -1.5 and confidence_tier != "low":
        signal = "mildly_bearish"
    else:
        signal = "neutral"

    return PredictionSummary(
        expected_price=round(final_predicted, 2),
        expected_return_pct=round(expected_return, 2),
        trend=trend,
        confidence_tier=confidence_tier,
        probability_up=round(probability_up, 2),
        signal=signal,
    )


async def build_prediction_response(
    payload: PredictRequest,
    *,
    settings: Settings,
    cache_backend: CacheBackend,
) -> PredictResponse:
    ticker = normalize_symbol_input(payload.symbol)
    _log_prediction_event(
        logging.INFO,
        "prediction.started",
        requested_symbol=ticker,
        asset_type=payload.asset_type,
        engine_requested=payload.engine,
        horizon_days=payload.horizon,
    )

    loop = asyncio.get_running_loop()
    market_series = await loop.run_in_executor(
        None,
        partial(
            fetch_close_prices,
            symbol=ticker,
            asset_type=payload.asset_type,
            cache_backend=cache_backend,
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
    degraded, degradation_code, degradation_message, degradation_reason = _degradation_fields(
        degraded=False,
    )
    evaluation = None

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

            if ml_metrics.validation_windows >= 2 and ml_metrics.directional_accuracy < 0.50:
                _log_prediction_event(
                    logging.WARNING,
                    "prediction.ml_quality_fallback",
                    symbol=market_series.resolved_symbol,
                    asset_type=payload.asset_type,
                    engine_requested=payload.engine,
                    engine_used="stat_fallback",
                    degradation_code="model_quality_insufficient",
                    directional_accuracy=round(ml_metrics.directional_accuracy, 4),
                    validation_windows=ml_metrics.validation_windows,
                )
                engine_used = "stat_fallback"
                model_name = "Statistical Fallback"
                engine_note = (
                    f"ML model did not pass quality check "
                    f"(directional accuracy {ml_metrics.directional_accuracy:.0%}). "
                    f"Fell back to statistical forecast."
                )
                forecast = stat_forecast
                (
                    degraded,
                    degradation_code,
                    degradation_message,
                    degradation_reason,
                ) = _degradation_fields(
                    degraded=True,
                    code="model_quality_insufficient",
                    message=(
                        "ML model quality was insufficient for production use. "
                        "Returned the statistical fallback forecast instead."
                    ),
                )
                source = PredictionSource(market_data=market_series.source, forecast="stat_fallback")
            else:
                engine_used = "ml"
                model_name = "Aurion Analog Forecaster"
                engine_note = (
                    f"Pattern-matching ML model using {ml_result.neighbors_used} nearest historical analogs "
                    f"with {len(market_series.close)} data points."
                )
                source = PredictionSource(market_data=market_series.source, forecast="ml_analog")

        except Exception as exc:
            _log_prediction_event(
                logging.WARNING,
                "prediction.ml_runtime_fallback",
                symbol=market_series.resolved_symbol,
                asset_type=payload.asset_type,
                engine_requested=payload.engine,
                engine_used="stat_fallback",
                degradation_code="ml_engine_unavailable",
                error=str(exc),
            )
            engine_used = "stat_fallback"
            model_name = "Statistical Fallback"
            engine_note = f"ML engine unavailable ({exc}). Fell back to statistical forecast."
            (
                degraded,
                degradation_code,
                degradation_message,
                degradation_reason,
            ) = _degradation_fields(
                degraded=True,
                code="ml_engine_unavailable",
                message=f"ML engine unavailable ({exc}). Fell back to statistical forecast.",
            )
            source = PredictionSource(market_data=market_series.source, forecast="stat_fallback")

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
            _log_prediction_event(
                logging.WARNING,
                "prediction.ai_fallback",
                symbol=market_series.resolved_symbol,
                asset_type=payload.asset_type,
                engine_requested=payload.engine,
                engine_used="stat_fallback",
                degradation_code="ai_provider_unavailable",
                error=exc.message,
            )
            engine_used = "stat_fallback"
            model_name = "Statistical Fallback"
            engine_note = f"AI unavailable ({exc.message}). Fell back to statistical forecast."
            (
                degraded,
                degradation_code,
                degradation_message,
                degradation_reason,
            ) = _degradation_fields(
                degraded=True,
                code="ai_provider_unavailable",
                message=f"AI unavailable ({exc.message}). Fell back to statistical forecast.",
            )
            source = PredictionSource(market_data=market_series.source, forecast="stat_fallback")

    summary = _build_summary(forecast, stats, evaluation)

    response = PredictResponse(
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
        degradation_code=degradation_code,
        degradation_message=degradation_message,
        degradation_reason=degradation_reason,
        history=history,
        forecast=forecast,
        stats=stats,
        summary=summary,
        evaluation=evaluation,
        disclaimer="This is a statistical/AI estimate and not financial advice. Past performance does not guarantee future results.",
    )
    _log_prediction_event(
        logging.INFO,
        "prediction.completed",
        symbol=response.symbol,
        asset_type=response.asset_type,
        engine_requested=response.engine_requested,
        engine_used=response.engine_used,
        degraded=response.degraded,
        degradation_code=response.degradation_code,
        market_data_source=response.source.market_data,
        forecast_source=response.source.forecast,
        validation_windows=response.evaluation.validation_windows if response.evaluation else None,
    )
    return response
