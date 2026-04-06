from __future__ import annotations

import numpy as np
import pandas as pd

from backend.ticker_catalog import AssetType


def backtest_stat_forecast(
    close: pd.Series,
    horizon: int,
    asset_type: AssetType,
    n_folds: int = 5,
) -> dict[str, float | int]:
    n = len(close)
    min_train = max(60, horizon * 3)
    fold_size = max(horizon, (n - min_train) // max(n_folds, 1))
    all_errors: list[float] = []
    all_actuals: list[float] = []
    fold_direction_scores: list[float] = []

    for fold in range(n_folds):
        test_end = n - (fold * fold_size)
        test_start = test_end - horizon
        train_end = test_start
        if train_end < min_train:
            break

        train_close = close.iloc[:train_end]
        _, forecast, _ = build_stat_forecast(train_close, horizon, asset_type)
        predicted = np.array([point["predicted"] for point in forecast], dtype=np.float64)
        actual = close.iloc[test_start:test_end].to_numpy(dtype=np.float64)
        actual_len = min(len(predicted), len(actual))
        if actual_len == 0:
            continue

        pred = predicted[:actual_len]
        act = actual[:actual_len]
        errors = np.abs(pred - act)
        all_errors.extend(errors.tolist())
        all_actuals.extend(np.abs(act).tolist())
        if actual_len > 1:
            pred_steps = np.sign(np.diff(pred))
            actual_steps = np.sign(np.diff(act))
            fold_direction_scores.append(float(np.mean(pred_steps == actual_steps)))

    if not all_errors:
        return {"mape": 0.0, "directional_accuracy": 0.5, "validation_windows": 0}

    errors_arr = np.array(all_errors, dtype=np.float64)
    actual_arr = np.array(all_actuals, dtype=np.float64)
    return {
        "mape": round(float(np.mean(errors_arr / np.maximum(actual_arr, 0.01))) * 100, 2),
        "directional_accuracy": round(
            float(np.mean(fold_direction_scores)) if fold_direction_scores else 0.5,
            4,
        ),
        "validation_windows": len(fold_direction_scores),
    }


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
        for dt, pred, low, high in zip(projected_dates, predicted, lower, upper, strict=False)
    ]

    stats = {
        "daily_trend_pct": round((float(np.exp(slope)) - 1.0) * 100.0, 3),
        "last_close": round(float(close.iloc[-1]), 2),
    }

    return history, forecast, stats
