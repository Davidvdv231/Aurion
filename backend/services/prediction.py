from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from functools import partial
from typing import Literal

from backend.config import Settings
from backend.errors import ServiceError
from backend.models import (
    EngineUsed,
    ExplanationFeature,
    ForecastPoint,
    HistoryPoint,
    PredictionEvaluation,
    PredictionExplanation,
    PredictionSource,
    PredictionSummary,
    PredictRequest,
    PredictResponse,
    PredictStats,
)
from backend.runtime import BlockingTaskRunner
from backend.services.ai import build_ai_forecast
from backend.services.cache import CacheBackend
from backend.services.forecast import backtest_stat_forecast, build_stat_forecast
from backend.services.market_data import fetch_close_prices, normalize_symbol_input
from backend.services.metrics import PredictionMetrics

logger = logging.getLogger("stock_predictor.prediction")


def _log_prediction_event(
    level: int, event: str, *, request_id: str | None = None, **fields: object
) -> None:
    clean_fields = {key: value for key, value in fields.items() if value is not None}
    details = " ".join(f"{key}={clean_fields[key]}" for key in sorted(clean_fields))
    message = event if not details else f"{event} {details}"
    extra: dict[str, object] = {
        "prediction_event": event,
        "request_id": request_id or "unknown",
        **{f"prediction_{key}": value for key, value in clean_fields.items()},
    }
    logger.log(level, message, extra=extra)


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
            signal="Neutral",
        )

    last_close = stats["last_close"]
    final_predicted = forecast[-1]["predicted"]
    expected_return = ((final_predicted / last_close) - 1.0) * 100 if last_close > 0 else 0.0

    trend: Literal["bullish", "bearish", "neutral"]
    if expected_return > 2.0:
        trend = "bullish"
    elif expected_return < -2.0:
        trend = "bearish"
    else:
        trend = "neutral"

    widths = [(pt["upper"] - pt["lower"]) / max(pt["predicted"], 0.01) for pt in forecast]
    avg_band_width = sum(widths) / len(widths)
    band_confidence = max(0.0, min(1.0, 1.0 - avg_band_width * 2))

    if evaluation and evaluation.directional_accuracy is not None:
        raw_confidence = (band_confidence + evaluation.directional_accuracy) / 2.0
    else:
        raw_confidence = band_confidence * 0.85

    confidence_tier: Literal["low", "medium", "high"]
    if raw_confidence >= 0.70:
        confidence_tier = "high"
    elif raw_confidence >= 0.45:
        confidence_tier = "medium"
    else:
        confidence_tier = "low"

    signal: Literal[
        "Strongly Bullish", "Bullish Outlook", "Neutral", "Bearish Outlook", "Strongly Bearish"
    ]
    if expected_return > 5.0 and confidence_tier == "high":
        signal = "Strongly Bullish"
    elif expected_return > 1.5 and confidence_tier != "low":
        signal = "Bullish Outlook"
    elif expected_return < -5.0 and confidence_tier == "high":
        signal = "Strongly Bearish"
    elif expected_return < -1.5 and confidence_tier != "low":
        signal = "Bearish Outlook"
    else:
        signal = "Neutral"

    return PredictionSummary(
        expected_price=round(final_predicted, 2),
        expected_return_pct=round(expected_return, 2),
        trend=trend,
        confidence_tier=confidence_tier,
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
    parts: list[str] = []

    if top_features:
        feature = top_features[0]
        label = _FEATURE_LABELS.get(feature.feature, feature.feature)
        if feature.relation == "similar":
            parts.append(f"{label} is close to the historical analog set.")
        elif feature.relation == "higher":
            parts.append(f"{label} is currently higher than the nearest analog set.")
        else:
            parts.append(f"{label} is currently lower than the nearest analog set.")

    parts.append(
        f"The {neighbors_used} closest historical patterns averaged a "
        f"{summary.expected_return_pct:+.1f}% move over the forecast horizon."
    )

    if summary.confidence_tier == "high":
        parts.append(
            "The analog forecast bands are relatively tight, so the pattern match is more stable."
        )
    elif summary.confidence_tier == "low":
        parts.append(
            "The analog forecast bands are wide, so this pattern comparison is less stable."
        )
    else:
        parts.append("The analog forecast bands are moderate, so the pattern comparison is mixed.")

    if nearest_analog_date:
        parts.append(f"Nearest analog period: {nearest_analog_date}.")

    return " ".join(parts)


def _build_explanation(meta: dict, summary: PredictionSummary) -> PredictionExplanation:
    return PredictionExplanation(
        top_features=meta["features"],
        neighbors_used=meta["neighbors_used"],
        avg_neighbor_distance=meta["avg_neighbor_distance"],
        nearest_analog_date=meta["nearest_analog_date"],
        narrative=_build_narrative(
            meta["features"],
            summary,
            meta["neighbors_used"],
            meta["nearest_analog_date"],
        ),
    )


async def _run_blocking(
    blocking_runner: BlockingTaskRunner,
    timeout_seconds: float,
    func,
):
    return await blocking_runner.run(func, timeout_seconds=timeout_seconds)


def _ml_quality_failure(
    evaluation: PredictionEvaluation,
    stat_baseline: dict[str, float | int],
) -> tuple[str, str] | None:
    validation_windows = evaluation.validation_windows or 0
    directional_accuracy = evaluation.directional_accuracy or 0.0
    mape = evaluation.mape

    if validation_windows < 3:
        return (
            "model_validation_insufficient",
            "ML validation coverage was insufficient for production use. Returned the statistical fallback forecast instead.",
        )
    if directional_accuracy < 0.45:
        return (
            "model_quality_insufficient",
            "ML directional accuracy was insufficient for production use. Returned the statistical fallback forecast instead.",
        )
    baseline_windows = int(stat_baseline.get("validation_windows", 0))
    baseline_mape = float(stat_baseline.get("mape", 0.0))
    if baseline_windows > 0 and mape is not None and mape > baseline_mape:
        return (
            "model_baseline_underperforming",
            "ML error quality did not beat the statistical baseline. Returned the statistical fallback forecast instead.",
        )
    return None


async def build_prediction_response(
    payload: PredictRequest,
    *,
    settings: Settings,
    cache_backend: CacheBackend,
    metrics: PredictionMetrics | None = None,
    blocking_runner: BlockingTaskRunner,
    request_id: str | None = None,
) -> PredictResponse:
    ticker = normalize_symbol_input(payload.symbol)
    t_start = time.perf_counter()
    _log_prediction_event(
        logging.INFO,
        "prediction.started",
        request_id=request_id,
        requested_symbol=ticker,
        asset_type=payload.asset_type,
        engine_requested=payload.engine,
        horizon_days=payload.horizon,
    )

    t_market = time.perf_counter()
    try:
        market_series = await _run_blocking(
            blocking_runner,
            settings.blocking_task_timeout_seconds,
            partial(
                fetch_close_prices,
                symbol=ticker,
                asset_type=payload.asset_type,
                cache_backend=cache_backend,
                settings=settings,
            ),
        )
    except asyncio.TimeoutError as exc:
        raise ServiceError(
            status_code=504,
            code="market_data_timeout",
            message="Market data lookup timed out.",
            retryable=True,
        ) from exc

    market_data_ms = round((time.perf_counter() - t_market) * 1000, 1)

    history, stat_forecast, stats = build_stat_forecast(
        market_series.close,
        payload.horizon,
        asset_type=payload.asset_type,
    )

    engine_used: EngineUsed = "stat"
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
    ml_explanation_meta: dict | None = None
    ml_analysis_summary: PredictionSummary | None = None
    model_ms: float | None = None

    if payload.engine == "ml":
        stat_baseline = backtest_stat_forecast(
            market_series.close,
            payload.horizon,
            payload.asset_type,
            n_folds=5,
        )
        try:
            from backend.ml.service import train_and_predict

            t_model = time.perf_counter()
            ml_result, ml_metrics = await _run_blocking(
                blocking_runner,
                settings.blocking_task_timeout_seconds,
                partial(
                    train_and_predict,
                    symbol=market_series.resolved_symbol,
                    close=market_series.close,
                    horizon=payload.horizon,
                    asset_type=payload.asset_type,
                ),
            )
            model_ms = round((time.perf_counter() - t_model) * 1000, 1)
            ml_forecast = [
                {
                    "date": ml_result.dates[i],
                    "predicted": round(float(ml_result.predicted[i]), 2),
                    "lower": round(float(ml_result.lower[i]), 2),
                    "upper": round(float(ml_result.upper[i]), 2),
                }
                for i in range(len(ml_result.dates))
            ]
            if len(ml_forecast) != payload.horizon:
                raise ValueError(
                    f"ML forecast horizon mismatch: expected {payload.horizon}, got {len(ml_forecast)}"
                )

            evaluation = PredictionEvaluation(
                mae=ml_metrics.mae,
                rmse=ml_metrics.rmse,
                mape=ml_metrics.mape,
                directional_accuracy=ml_metrics.directional_accuracy,
                validation_windows=ml_metrics.validation_windows,
            )
            ml_analysis_summary = _build_summary(ml_forecast, stats, evaluation)
            ml_explanation_meta = {
                "neighbors_used": ml_result.neighbors_used,
                "avg_neighbor_distance": ml_result.avg_neighbor_distance,
                "nearest_analog_date": ml_result.nearest_analog_date,
                "features": [
                    ExplanationFeature(
                        feature=fc.feature,
                        difference_score=fc.difference_score,
                        value=fc.value,
                        relation=fc.relation,
                    )
                    for fc in ml_result.top_features
                ],
            }

            _log_prediction_event(
                logging.INFO,
                "prediction.ml_quality_check",
                request_id=request_id,
                symbol=market_series.resolved_symbol,
                directional_accuracy=round(ml_metrics.directional_accuracy, 4),
                validation_windows=ml_metrics.validation_windows,
                mape=round(ml_metrics.mape, 2) if ml_metrics.mape else None,
                baseline_mape=stat_baseline.get("mape"),
                baseline_windows=stat_baseline.get("validation_windows"),
            )
            quality_failure = _ml_quality_failure(evaluation, stat_baseline)
            if quality_failure is not None:
                degradation_code, degradation_message = quality_failure
                _log_prediction_event(
                    logging.WARNING,
                    "prediction.ml_quality_fallback",
                    request_id=request_id,
                    symbol=market_series.resolved_symbol,
                    asset_type=payload.asset_type,
                    engine_requested=payload.engine,
                    engine_used="stat_fallback",
                    degradation_code=degradation_code,
                    directional_accuracy=round(ml_metrics.directional_accuracy, 4),
                    validation_windows=ml_metrics.validation_windows,
                    baseline_mape=stat_baseline.get("mape"),
                )
                engine_used = "stat_fallback"
                model_name = "Statistical Fallback"
                engine_note = degradation_message
                forecast = stat_forecast
                (
                    degraded,
                    degradation_code,
                    degradation_message,
                    degradation_reason,
                ) = _degradation_fields(
                    degraded=True,
                    code=degradation_code,
                    message=degradation_message,
                )
                source = PredictionSource(
                    market_data=market_series.source,
                    forecast="stat_fallback",
                    analysis="ml_pattern_difference",
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
                forecast = ml_forecast
                source = PredictionSource(
                    market_data=market_series.source,
                    forecast="ml_analog",
                    analysis="ml_pattern_difference",
                    data_quality=market_series.data_quality,
                    data_warnings=market_series.data_warnings,
                    stale=market_series.stale,
                )
        except asyncio.TimeoutError:
            _log_prediction_event(
                logging.WARNING,
                "prediction.ml_runtime_fallback",
                request_id=request_id,
                symbol=market_series.resolved_symbol,
                asset_type=payload.asset_type,
                engine_requested=payload.engine,
                engine_used="stat_fallback",
                degradation_code="ml_engine_timeout",
            )
            engine_used = "stat_fallback"
            model_name = "Statistical Fallback"
            engine_note = "ML engine timed out. Fell back to statistical forecast."
            (
                degraded,
                degradation_code,
                degradation_message,
                degradation_reason,
            ) = _degradation_fields(
                degraded=True,
                code="ml_engine_timeout",
                message="ML engine timed out. Fell back to statistical forecast.",
            )
            source = PredictionSource(
                market_data=market_series.source,
                forecast="stat_fallback",
                analysis=None,
                data_quality=market_series.data_quality,
                data_warnings=market_series.data_warnings,
                stale=market_series.stale,
            )
        except Exception as exc:
            _log_prediction_event(
                logging.WARNING,
                "prediction.ml_runtime_fallback",
                request_id=request_id,
                symbol=market_series.resolved_symbol,
                asset_type=payload.asset_type,
                engine_requested=payload.engine,
                engine_used="stat_fallback",
                degradation_code="ml_engine_unavailable",
                error=str(exc),
            )
            engine_used = "stat_fallback"
            model_name = "Statistical Fallback"
            engine_note = "ML engine encountered an error. Fell back to statistical forecast."
            (
                degraded,
                degradation_code,
                degradation_message,
                degradation_reason,
            ) = _degradation_fields(
                degraded=True,
                code="ml_engine_unavailable",
                message="ML engine encountered an error. Fell back to statistical forecast.",
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
            ai_forecast, ai_model = await _run_blocking(
                blocking_runner,
                settings.blocking_task_timeout_seconds,
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
            if len(ai_forecast) != payload.horizon:
                raise ServiceError(
                    status_code=502,
                    code="provider_invalid_response",
                    message="AI engine returned an unexpected forecast horizon.",
                    retryable=True,
                )
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
        except asyncio.TimeoutError:
            _log_prediction_event(
                logging.WARNING,
                "prediction.ai_fallback",
                request_id=request_id,
                symbol=market_series.resolved_symbol,
                asset_type=payload.asset_type,
                engine_requested=payload.engine,
                engine_used="stat_fallback",
                degradation_code="ai_provider_timeout",
            )
            engine_used = "stat_fallback"
            model_name = "Statistical Fallback"
            engine_note = "AI provider timed out. Fell back to statistical forecast."
            (
                degraded,
                degradation_code,
                degradation_message,
                degradation_reason,
            ) = _degradation_fields(
                degraded=True,
                code="ai_provider_timeout",
                message="AI provider timed out. Fell back to statistical forecast.",
            )
            source = PredictionSource(
                market_data=market_series.source,
                forecast="stat_fallback",
                analysis=None,
                data_quality=market_series.data_quality,
                data_warnings=market_series.data_warnings,
                stale=market_series.stale,
            )
        except ServiceError as exc:
            _log_prediction_event(
                logging.WARNING,
                "prediction.ai_fallback",
                request_id=request_id,
                symbol=market_series.resolved_symbol,
                asset_type=payload.asset_type,
                engine_requested=payload.engine,
                engine_used="stat_fallback",
                degradation_code="ai_provider_unavailable",
                error=exc.message,
            )
            engine_used = "stat_fallback"
            model_name = "Statistical Fallback"
            engine_note = (
                "AI provider is temporarily unavailable. Fell back to statistical forecast."
            )
            (
                degraded,
                degradation_code,
                degradation_message,
                degradation_reason,
            ) = _degradation_fields(
                degraded=True,
                code="ai_provider_unavailable",
                message="AI provider is temporarily unavailable. Fell back to statistical forecast.",
            )
            source = PredictionSource(
                market_data=market_series.source,
                forecast="stat_fallback",
                analysis=None,
                data_quality=market_series.data_quality,
                data_warnings=market_series.data_warnings,
                stale=market_series.stale,
            )
        except Exception as exc:
            _log_prediction_event(
                logging.WARNING,
                "prediction.ai_fallback",
                request_id=request_id,
                symbol=market_series.resolved_symbol,
                asset_type=payload.asset_type,
                engine_requested=payload.engine,
                engine_used="stat_fallback",
                degradation_code="ai_engine_unavailable",
                error=str(exc),
            )
            engine_used = "stat_fallback"
            model_name = "Statistical Fallback"
            engine_note = "AI engine encountered an error. Fell back to statistical forecast."
            (
                degraded,
                degradation_code,
                degradation_message,
                degradation_reason,
            ) = _degradation_fields(
                degraded=True,
                code="ai_engine_unavailable",
                message="AI engine encountered an error. Fell back to statistical forecast.",
            )
            source = PredictionSource(
                market_data=market_series.source,
                forecast="stat_fallback",
                analysis=None,
                data_quality=market_series.data_quality,
                data_warnings=market_series.data_warnings,
                stale=market_series.stale,
            )

    if len(forecast) != payload.horizon:
        raise ServiceError(
            status_code=500,
            code="forecast_horizon_mismatch",
            message="Forecast horizon mismatch.",
        )

    summary = _build_summary(forecast, stats, evaluation)
    if ml_explanation_meta is not None and ml_analysis_summary is not None:
        explanation = _build_explanation(ml_explanation_meta, ml_analysis_summary)

    # --- Currency conversion ---
    native_currency = market_series.currency
    display_currency = payload.display_currency.upper()

    if display_currency != native_currency.upper():
        from backend.services.exchange_rates import convert_price, get_exchange_rate

        rate = get_exchange_rate(native_currency, display_currency)
        if rate != 1.0:
            # Convert history close prices
            for pt in history:
                pt["close"] = convert_price(pt["close"], rate)
            # Convert forecast prices
            for pt in forecast:
                pt["predicted"] = convert_price(pt["predicted"], rate)
                pt["lower"] = convert_price(pt["lower"], rate)
                pt["upper"] = convert_price(pt["upper"], rate)
            # Convert stats
            if stats.get("last_close") is not None:
                stats["last_close"] = round(stats["last_close"] * rate, 6)
            # Rebuild summary with converted prices
            summary = _build_summary(forecast, stats, evaluation)
        response_currency = display_currency
    else:
        response_currency = native_currency

    history_points = [HistoryPoint.model_validate(point) for point in history]
    forecast_points = [ForecastPoint.model_validate(point) for point in forecast]
    stats_model = PredictStats.model_validate(stats)

    response = PredictResponse(
        symbol=market_series.resolved_symbol,
        requested_symbol=ticker,
        asset_type=payload.asset_type,
        currency=response_currency,
        native_currency=native_currency,
        display_currency=response_currency,
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
        history=history_points,
        forecast=forecast_points,
        stats=stats_model,
        summary=summary,
        evaluation=evaluation,
        explanation=explanation,
        disclaimer="This is an estimate and not financial advice. Past performance does not guarantee future results.",
    )
    total_ms = round((time.perf_counter() - t_start) * 1000, 1)
    _log_prediction_event(
        logging.INFO,
        "prediction.completed",
        request_id=request_id,
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
