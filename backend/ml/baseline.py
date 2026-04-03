from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(slots=True)
class ForecastPoint:
    date: str
    predicted: float
    lower: float
    upper: float


@dataclass(slots=True)
class BaselineForecast:
    model_name: str
    summary: dict[str, float]
    path: list[ForecastPoint]


def build_statistical_baseline(close: pd.Series, horizon: int, asset_type: str) -> BaselineForecast:
    values = close.astype(float).to_numpy()
    if values.size < 5:
        raise ValueError("close series is too short for a baseline forecast.")

    log_values = np.log(values)
    x = np.arange(len(log_values), dtype=float)
    slope, intercept = np.polyfit(x, log_values, 1)
    fitted = intercept + slope * x
    residuals = log_values - fitted
    sigma = float(np.std(residuals, ddof=1)) if residuals.size > 1 else 0.01
    sigma = max(sigma, 0.01)

    if asset_type == "crypto":
        future_dates = pd.date_range(close.index[-1] + pd.Timedelta(days=1), periods=horizon, freq="D")
    else:
        future_dates = pd.bdate_range(close.index[-1] + pd.Timedelta(days=1), periods=horizon)

    future_x = np.arange(len(log_values), len(log_values) + horizon, dtype=float)
    future_log = intercept + slope * future_x
    predicted = np.exp(future_log)
    lower = np.exp(future_log - (1.28 * sigma))
    upper = np.exp(future_log + (1.28 * sigma))

    path = [
        ForecastPoint(
            date=dt.date().isoformat(),
            predicted=float(round(pred, 4)),
            lower=float(round(low, 4)),
            upper=float(round(high, 4)),
        )
        for dt, pred, low, high in zip(future_dates, predicted, lower, upper, strict=False)
    ]

    summary = {
        "last_close": float(values[-1]),
        "daily_trend_pct": float((np.exp(slope) - 1.0) * 100.0),
        "sigma": sigma,
    }
    return BaselineForecast(model_name="statistical_baseline", summary=summary, path=path)
