from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import math
import time
from functools import partial

from backend.config import Settings
from backend.errors import ServiceError
from backend.models import (
    ExplanationFeature,
    PredictRequest,
    PredictResponse,
    PredictionEvaluation,
    PredictionExplanation,
    PredictionSource,
    PredictionSummary,
)
from backend.services.ai import build_ai_forecast
from backend.services.cache import CacheBackend
from backend.services.forecast import build_stat_forecast
from backend.services.market_data import fetch_close_prices, normalize_symbol_input
from backend.services.metrics import PredictionMetrics

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


_FEATURE_LABELS: dict[str, str] = {
    "rsi_14": "RSI (14)",
    "macd": "MACD line",
    "macd_signal": "MACD signal",
    "macd_hist": "MACD histogram",
    "momentum_10": "10-day momentum",
    "bb_bandwidth": "Bollinger bandwidth",
    "bb_position": "Bollinger position",
    "volatility_5": "5-day volatility",
    "volatility_20": "20-day volatility",
    "return_1": "1-day return",
    "return_5": "5-day return",
    "sma_5": "SMA-5 gap",
    "sma_10": "SMA-10 gap",
    "sma_20": "SMA-20 gap",
    "sma_50": "SMA-50 gap",
    "ema_12": "EMA-12 gap",
    "ema_26": "EMA-26 gap",
    "volume_change_5": "5-day volume change",
    "volume_zscore_20": "Volume z-score (20)",
    "price_to_sma_20": "Price-to-SMA20 ratio",
    "high_low_range": "High-low range",
    "close_open_gap": "Close-open gap",
    "log_return_1": "Log return (1d)",
}


def _build_narrative(
    top_features: list[ExplanationFeature],
    summary: PredictionSummary,
    neighbors_used: int,
    nearest_analog_date: str,
) -> str:
    """Generate a plain-English explanation of the prediction."""
    parts: list[str] = []

    # Lead with the most influential feature
    if top_features:
        f = top_features[0]
        label = _FEATURE_LABELS.get(f.feature, f.feature)
        if f.feature == "rsi_14":
            rsi_val = f.value
            if rsi_val > 70:
                parts.append(f"{label} at {rsi_val:.0f} suggests overbought conditions.")
            elif rsi_val < 30:
                parts.append(f"{label} at {rsi_val:.0f} suggests oversold conditions.")
            else:
                parts.append(f"{label} at {rsi_val:.0f} is in a neutral zone.")
        elif "volatility" in f.feature:
            parts.append(f"{label} is elevated, widening the uncertainty range.")
        elif "momentum" in f.feature or "return" in f.feature:
            direction = "positive" if f.value > 0 else "negative"
            parts.append(f"{label} is {direction} ({f.value:+.2%}), driving the signal.")
        else:
            parts.append(f"{label} is the strongest differentiator from historical analogs.")

    # Analog context
    parts.append(
        f"The {neighbors_used} closest historical patterns averaged a "
        f"{summary.expected_return_pct:+.1f}% move over the forecast horizon."
    )

    # Confidence reasoning
    tier = summary.confidence_tier
    if tier == "high":
        parts.append("Confidence is high because forecast bands are tight relative to expected return.")
    elif tier == "low":
        parts.append("Confidence is low because bands are wide — the outcome is uncertain.")
    else:
        parts.append("Confidence is medium — bands are moderate relative to expected return.")

    if nearest_analog_date:
        parts.append(f"Nearest analog period: {nearest_analog_date}.")

    return " ".join(parts)


def _build_explanation(meta: dict, summary: PredictionSummary) -> PredictionExplanation:
    narrative = _build_narrative(
        meta["features"],
        summary,
        meta["neighbors_used"],
        meta["nearest_analog_date"],
    )
    return PredictionExplanation(
        top_features=meta["features"],
        neighbors_used=meta["neighbors_used"],
        avg_neighbor_distance=meta["avg_neighbor_distance"],
        nearest_analog_date=meta["nearest_analog_date"],
        narrative=narrative,
    )


async def build_prediction_response(
    payload: PredictRequest,
    *,
    settings: Settings,
    cache_backend: CacheBackend,
    metrics: PredictionMetrics | None = None,
) -> PredictResponse:
    ticker = normalize_symbol_input(payload.symbol)
    t_start = time.perf_counter()
    _log_prediction_event(
        logging.INFO,
        "prediction.started",
        requested_symbol=ticker,
        asset_type=payload.asset_type,
        engine_requested=payload.engine,
        horizon_days=payload.horizon,
    )

    loop = asyncio.get_running_loop()
    t_market = time.perf_counter()
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

    market_data_ms = round((time.perf_counter() - t_market) * 1000, 1)

    history, stat_forecast, stats = build_stat_forecast(
        market_series.close,
        payload.horizon,
        asset_type=payload.asset_type,
    )

    engine_used = "stat"
    model_name = "Statistical Trend"
    engine_note = "Log-linear statistical trend model on historical prices."
    forecast = stat_forecast
    source = PredictionSource(
        market_data=market_series.source,
        forecast="stat",
        analysis=None,
        data_quality=market_series.data_quality,
        data_warnings=market_series.data_warnings,
        stale=market_series.stale,
    )
    degraded, degradation_code, degradation_message, degradation_reason = _degradation_fields(
        degraded=False,
    )
    evaluation = None
    explanation = None
    _ml_explain_meta: dict | None = None
    model_ms: float | None = None

    if payload.engine == "ml":
        try:
            from backend.ml.service import train_and_predict

            t_model = time.perf_counter()
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

            model_ms = round((time.perf_counter() - t_model) * 1000, 1)
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
            ml_summary = _build_summary(forecast, stats, evaluation)
            _ml_explain_meta = {
                "neighbors_used": ml_result.neighbors_used,
                "avg_neighbor_distance": ml_result.avg_neighbor_distance,
                "nearest_analog_date": ml_result.nearest_analog_date,
                "features": [
                    ExplanationFeature(
                        feature=fc.feature,
                        contribution=fc.contribution,
                        value=fc.value,
                        direction=fc.direction,
                    )
                    for fc in ml_result.top_features
                ],
                "summary": ml_summary,
            }

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
                source = PredictionSource(
                    market_data=market_series.source,
                    forecast="stat_fallback",
                    analysis="ml_analog",
                    data_quality=market_series.data_quality,
                    data_warnings=market_series.data_warnings,
                    stale=market_series.stale,
                )
            else:
                engine_used = "ml"
                model_name = "Aurion Analog Forecaster"
                engine_note = (
                    f"Pattern-matching ML model using {ml_result.neighbors_used} nearest historical analogs "
                    f"with {len(market_series.close)} data points."
                )
                source = PredictionSource(
                    market_data=market_series.source,
                    forecast="ml_analog",
                    analysis="ml_analog",
                    data_quality=market_series.data_quality,
                    data_warnings=market_series.data_warnings,
                    stale=market_series.stale,
                )

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
            source = PredictionSource(
                market_data=market_series.source,
                forecast="stat_fallback",
                analysis=None,
                data_quality=market_series.data_quality,
                data_warnings=market_series.data_warnings,
                stale=market_series.stale,
            )

    elif payload.engine == "ai":
        try:
            t_model = time.perf_counter()
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
            model_ms = round((time.perf_counter() - t_model) * 1000, 1)
            forecast = ai_forecast
            engine_used = "ai"
            model_name = ai_model["model"]
            engine_note = f"AI forecast via {ai_model['provider']} ({ai_model['model']})."
            source = PredictionSource(
                market_data=market_series.source,
                forecast=ai_model["source"],
                analysis=None,
                data_quality=market_series.data_quality,
                data_warnings=market_series.data_warnings,
                stale=market_series.stale,
            )
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
            source = PredictionSource(
                market_data=market_series.source,
                forecast="stat_fallback",
                analysis=None,
                data_quality=market_series.data_quality,
                data_warnings=market_series.data_warnings,
                stale=market_series.stale,
            )

    summary = _build_summary(forecast, stats, evaluation)

    if _ml_explain_meta is not None:
        explanation = _build_explanation(_ml_explain_meta, _ml_explain_meta["summary"])

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
        explanation=explanation,
        disclaimer="This is a statistical/AI estimate and not financial advice. Past performance does not guarantee future results.",
    )
    total_ms = round((time.perf_counter() - t_start) * 1000, 1)
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
        analysis_source=response.source.analysis,
        data_quality=response.source.data_quality,
        stale=response.source.stale,
        validation_windows=response.evaluation.validation_windows if response.evaluation else None,
        market_data_ms=market_data_ms,
        model_ms=model_ms,
        total_ms=total_ms,
    )
    if metrics is not None:
        metrics.record_prediction(
            engine_used=response.engine_used,
            total_ms=total_ms,
            degraded=response.degraded,
            degradation_code=response.degradation_code,
        )
    return response
