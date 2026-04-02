from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from backend.config import Settings
from backend.errors import ServiceError
from backend.ml.service import ForecastServiceResult, train_and_validate_model
from backend.services.forecast import build_evaluation_summary
from backend.services.market_data import MarketHistory
from backend.ticker_catalog import AssetType


@dataclass(slots=True)
class MLPredictionResult:
    history: list[dict]
    forecast: list[dict]
    stats: dict
    summary: dict
    evaluation: dict | None
    model_name: str
    model_version: str | None
    engine_note: str
    forecast_source: str


def build_ml_prediction(
    market_history: MarketHistory,
    *,
    symbol: str,
    asset_type: AssetType,
    horizon: int,
    settings: Settings,
) -> MLPredictionResult:
    ohlcv = market_history.frame.copy()
    ohlcv.columns = [str(column).lower() for column in ohlcv.columns]
    ohlcv = ohlcv.sort_index()

    if len(ohlcv) < settings.ml_min_history_rows:
        raise ServiceError(
            status_code=400,
            code="insufficient_history",
            message=(
                "Onvoldoende historiek voor de ML-forecasting engine. "
                f"Minstens {settings.ml_min_history_rows} datapunten vereist."
            ),
            provider="ml",
        )

    registry_root = Path(settings.artifacts_root) / "models" / asset_type / symbol.replace("/", "_")
    lookback = min(60, max(30, horizon * 3))
    service_result = train_and_validate_model(
        ohlcv,
        asset_type=asset_type,
        lookback=lookback,
        horizon=horizon,
        top_k=settings.ml_neighbor_count,
        registry_root=registry_root,
        persist=True,
    )
    forecast_output = service_result.model.predict(ohlcv, asset_type=asset_type, top_k=settings.ml_neighbor_count)

    history = _build_history_payload(ohlcv["close"], asset_type)
    forecast = [
        {
            "date": point.date,
            "predicted": round(float(point.predicted), 2),
            "lower": round(float(point.lower), 2),
            "upper": round(float(point.upper), 2),
        }
        for point in forecast_output.path
    ]
    summary = {
        "expected_price": round(float(forecast_output.path[-1].predicted), 2),
        "expected_return_pct": round(float(forecast_output.summary["expected_return_pct"]), 3),
        "trend": str(forecast_output.summary["trend"]),
        "confidence_score": round(float(forecast_output.summary["confidence"]), 3),
        "probability_up": round(float(forecast_output.summary["probability_up"]), 3),
        "signal": str(forecast_output.summary["signal"]),
    }
    stats = {
        "daily_trend_pct": round(float(forecast_output.summary["daily_trend_pct"]), 3),
        "last_close": round(float(forecast_output.summary["last_close"]), 2),
    }
    evaluation = _build_ml_evaluation(service_result, horizon)
    model_version = service_result.artifact.version if service_result.artifact is not None else None
    engine_note = (
        "Hybride ML-ensemble op OHLCV-data: sequence analogs, regime-kernel regressie "
        "en walk-forward validatie."
    )
    return MLPredictionResult(
        history=history,
        forecast=forecast,
        stats=stats,
        summary=summary,
        evaluation=evaluation,
        model_name="Hybrid Regime Ensemble",
        model_version=model_version,
        engine_note=engine_note,
        forecast_source="ml_hybrid",
    )


def _build_history_payload(close: pd.Series, asset_type: AssetType) -> list[dict]:
    history_window = close.tail(365 if asset_type == "crypto" else 260)
    return [
        {"date": idx.date().isoformat(), "close": round(float(price), 2)}
        for idx, price in history_window.items()
    ]


def _build_ml_evaluation(service_result: ForecastServiceResult, horizon: int) -> dict | None:
    if service_result.backtest is None:
        return None

    metrics = dict(service_result.backtest.metrics)
    metrics["mae"] = metrics.get("overall_mae", metrics.get("mae"))
    metrics["rmse"] = metrics.get("overall_rmse", metrics.get("rmse"))
    metrics["mape"] = metrics.get("overall_mape", metrics.get("mape"))
    metrics["sample_size"] = len(service_result.backtest.folds) * horizon
    metrics["windows"] = len(service_result.backtest.folds)
    return build_evaluation_summary(metrics)
