from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from backend.ml.metrics import directional_accuracy, mae, mape, rmse
from backend.ml.model import AnalogForecastModel, ForecastOutput


@dataclass(slots=True)
class FoldResult:
    anchor_date: str
    metrics: dict[str, float]
    forecast: ForecastOutput


@dataclass(slots=True)
class BacktestResult:
    model_name: str
    folds: list[FoldResult] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


def walk_forward_backtest(
    ohlcv: pd.DataFrame,
    model_factory: Callable[[], AnalogForecastModel],
    *,
    min_train_size: int = 120,
    step: int = 5,
    max_folds: int = 8,
) -> BacktestResult:
    if min_train_size <= 0:
        raise ValueError("min_train_size must be positive.")
    if step <= 0:
        raise ValueError("step must be positive.")
    if max_folds <= 0:
        raise ValueError("max_folds must be positive.")

    prototype = model_factory()
    horizon = prototype.horizon
    if len(ohlcv) <= min_train_size:
        raise ValueError("Not enough rows for backtesting.")

    folds: list[FoldResult] = []
    aggregate_actual: list[float] = []
    aggregate_predicted: list[float] = []
    aggregate_fold_metrics: list[dict[str, float]] = []

    for fold_count, anchor_end in enumerate(range(min_train_size, len(ohlcv) - 1, step), start=1):
        if fold_count > max_folds:
            break
        train_frame = ohlcv.iloc[: anchor_end + 1].copy()
        future_slice = ohlcv.iloc[anchor_end + 1 : anchor_end + 1 + horizon]
        if len(future_slice) < horizon:
            break

        model = model_factory()
        model.fit(train_frame)
        forecast = model.predict(train_frame)
        actual_prices = future_slice["close"].astype(float).to_numpy()
        predicted_prices = np.asarray([point.predicted for point in forecast.path], dtype=float)
        origin_price = float(train_frame["close"].iloc[-1])

        fold_metrics = {
            "mae": mae(actual_prices, predicted_prices),
            "rmse": rmse(actual_prices, predicted_prices),
            "mape": mape(actual_prices, predicted_prices),
            "directional_accuracy": directional_accuracy(
                np.r_[origin_price, actual_prices],
                np.r_[origin_price, predicted_prices],
            ),
        }
        folds.append(
            FoldResult(
                anchor_date=str(train_frame.index[-1].date()) if hasattr(train_frame.index[-1], "date") else str(train_frame.index[-1]),
                metrics=fold_metrics,
                forecast=forecast,
            )
        )
        aggregate_actual.extend(actual_prices.tolist())
        aggregate_predicted.extend(predicted_prices.tolist())
        aggregate_fold_metrics.append(fold_metrics)

    if not folds:
        raise ValueError("Backtest could not produce any folds.")

    metrics = {
        key: float(np.mean([fold[key] for fold in aggregate_fold_metrics]))
        for key in ("mae", "rmse", "mape", "directional_accuracy")
    }
    metrics["overall_mae"] = mae(aggregate_actual, aggregate_predicted)
    metrics["overall_rmse"] = rmse(aggregate_actual, aggregate_predicted)
    metrics["overall_mape"] = mape(aggregate_actual, aggregate_predicted)

    return BacktestResult(model_name=prototype.model_name, folds=folds, metrics=metrics)
