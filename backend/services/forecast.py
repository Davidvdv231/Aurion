from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from backend.errors import ServiceError
from backend.ticker_catalog import AssetType


def future_dates(last_date: pd.Timestamp, horizon: int, asset_type: AssetType) -> pd.DatetimeIndex:
    if asset_type == "crypto":
        return pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon, freq="D")
    return pd.bdate_range(last_date + pd.Timedelta(days=1), periods=horizon)


def build_stat_forecast(
    close: pd.Series,
    horizon: int,
    asset_type: AssetType,
) -> tuple[list[dict], list[dict], dict]:
    values = close.astype(float).to_numpy()
    log_values = np.log(values)

    x = np.arange(len(log_values), dtype=float)
    slope, intercept = np.polyfit(x, log_values, 1)

    fitted = intercept + (slope * x)
    residuals = log_values - fitted
    sigma = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.01
    sigma = max(sigma, 0.01)

    future_x = np.arange(len(log_values), len(log_values) + horizon, dtype=float)
    future_log = intercept + (slope * future_x)

    z_score_80 = 1.28
    predicted = np.exp(future_log)
    lower = np.exp(future_log - z_score_80 * sigma)
    upper = np.exp(future_log + z_score_80 * sigma)

    history_window = close.tail(365 if asset_type == "crypto" else 260)
    history = [
        {
            "date": idx.date().isoformat(),
            "close": round(float(price), 2),
        }
        for idx, price in history_window.items()
    ]

    projected_dates = future_dates(close.index[-1], horizon, asset_type)
    forecast = [
        {
            "date": dt.date().isoformat(),
            "predicted": round(float(pred), 2),
            "lower": round(float(low), 2),
            "upper": round(float(high), 2),
        }
        for dt, pred, low, high in zip(projected_dates, predicted, lower, upper)
    ]

    stats = {
        "daily_trend_pct": round((float(np.exp(slope)) - 1.0) * 100.0, 3),
        "last_close": round(float(close.iloc[-1]), 2),
    }

    return history, forecast, stats


def normalize_ai_forecast_rows(
    forecast_rows: list,
    close: pd.Series,
    horizon: int,
    asset_type: AssetType,
    provider: str,
) -> list[dict]:
    if len(forecast_rows) < horizon:
        raise ServiceError(
            status_code=502,
            code="provider_invalid_response",
            message="AI engine antwoord moet een forecast lijst met voldoende punten bevatten.",
            provider=provider,
            retryable=True,
        )

    daily_vol = float(close.pct_change().dropna().tail(120).std())
    if np.isnan(daily_vol) or daily_vol <= 0:
        daily_vol = 0.015

    z_score_80 = 1.28
    projected_dates = future_dates(close.index[-1], horizon, asset_type)
    normalized_forecast: list[dict] = []

    for index in range(horizon):
        row = forecast_rows[index]
        if not isinstance(row, dict):
            raise ServiceError(
                status_code=502,
                code="provider_invalid_response",
                message="AI engine forecast-formaat is ongeldig.",
                provider=provider,
                retryable=True,
            )

        predicted_raw = row.get("predicted", row.get("close"))
        try:
            predicted = max(0.01, float(predicted_raw))
        except (TypeError, ValueError) as exc:
            raise ServiceError(
                status_code=502,
                code="provider_invalid_response",
                message="AI engine voorspelling bevat geen geldig getal.",
                provider=provider,
                retryable=True,
            ) from exc

        date_raw = row.get("date")
        if date_raw is None:
            date_iso = projected_dates[index].date().isoformat()
        elif not isinstance(date_raw, str):
            raise ServiceError(
                status_code=502,
                code="provider_invalid_response",
                message="AI engine datumformaat is ongeldig.",
                provider=provider,
                retryable=True,
            )
        else:
            try:
                date_iso = date.fromisoformat(date_raw[:10]).isoformat()
            except ValueError as exc:
                raise ServiceError(
                    status_code=502,
                    code="provider_invalid_response",
                    message="AI engine datumformaat is ongeldig.",
                    provider=provider,
                    retryable=True,
                ) from exc

        lower_raw = row.get("lower")
        upper_raw = row.get("upper")
        try:
            lower = float(lower_raw) if lower_raw is not None else predicted * (1 - z_score_80 * daily_vol)
            upper = float(upper_raw) if upper_raw is not None else predicted * (1 + z_score_80 * daily_vol)
        except (TypeError, ValueError) as exc:
            raise ServiceError(
                status_code=502,
                code="provider_invalid_response",
                message="AI engine bandwaarden zijn ongeldig.",
                provider=provider,
                retryable=True,
            ) from exc

        lower = max(0.01, lower)
        upper = max(lower + 0.01, upper)

        normalized_forecast.append(
            {
                "date": date_iso,
                "predicted": round(predicted, 2),
                "lower": round(lower, 2),
                "upper": round(upper, 2),
            }
        )

    return normalized_forecast


def build_prediction_summary(
    forecast: list[dict],
    last_close: float,
    probability_up: float | None = None,
) -> dict | None:
    if not forecast:
        return None

    final_point = forecast[-1]
    expected_price = float(final_point["predicted"])
    expected_return_pct = ((expected_price / max(last_close, 0.01)) - 1.0) * 100.0

    if probability_up is None:
        probability_up = 0.5
        if expected_return_pct > 0.3:
            probability_up = 0.58
        elif expected_return_pct < -0.3:
            probability_up = 0.42

    interval_width_pct = ((float(final_point["upper"]) - float(final_point["lower"])) / max(expected_price, 0.01)) * 100.0
    confidence_score = max(0.15, min(0.95, abs(probability_up - 0.5) * 2.0 * max(0.2, 1.0 - (interval_width_pct / 35.0))))

    if probability_up >= 0.58 and expected_return_pct >= 1.0:
        trend = "bullish"
        signal = "buy"
    elif probability_up <= 0.42 and expected_return_pct <= -1.0:
        trend = "bearish"
        signal = "sell"
    else:
        trend = "neutral"
        signal = "hold"

    return {
        "expected_price": round(expected_price, 2),
        "expected_return_pct": round(expected_return_pct, 3),
        "trend": trend,
        "confidence_score": round(confidence_score, 3),
        "probability_up": round(float(probability_up), 3),
        "signal": signal,
    }


def build_evaluation_summary(
    metrics: dict | None,
    benchmark_metrics: dict | None = None,
) -> dict | None:
    if not metrics:
        return None

    return {
        "mae": _rounded_metric(metrics.get("mae")),
        "rmse": _rounded_metric(metrics.get("rmse")),
        "mape": _rounded_metric(metrics.get("mape")),
        "directional_accuracy": _rounded_metric(metrics.get("directional_accuracy")),
        "benchmark_mae": _rounded_metric((benchmark_metrics or {}).get("mae")),
        "benchmark_directional_accuracy": _rounded_metric((benchmark_metrics or {}).get("directional_accuracy")),
        "sample_size": _int_metric(metrics.get("sample_size")),
        "validation_windows": _int_metric(metrics.get("windows")),
    }


def _rounded_metric(value: float | int | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _int_metric(value: float | int | None) -> int | None:
    if value is None:
        return None
    return int(value)
