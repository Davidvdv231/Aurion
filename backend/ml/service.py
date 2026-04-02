"""High-level ML service: train, cache, and predict."""
from __future__ import annotations

import logging
from threading import Lock

import pandas as pd

from backend.ml.model import AnalogForecastModel, BacktestMetrics, ForecastResult
from backend.ticker_catalog import AssetType

logger = logging.getLogger("stock_predictor.ml")

# In-memory model cache keyed by (asset_type, symbol)
_model_cache: dict[tuple[str, str], AnalogForecastModel] = {}
_model_lock = Lock()

MIN_HISTORY_ROWS = 180


def train_and_predict(
    symbol: str,
    close: pd.Series,
    horizon: int,
    asset_type: AssetType,
    ohlcv: pd.DataFrame | None = None,
    n_neighbors: int = 24,
    lookback: int = 60,
    backtest_folds: int = 5,
) -> tuple[ForecastResult, BacktestMetrics]:
    """Train (or reuse) a model for the given symbol and return predictions."""
    if len(close) < MIN_HISTORY_ROWS:
        raise ValueError(
            f"Need at least {MIN_HISTORY_ROWS} data points, got {len(close)}"
        )

    cache_key = (asset_type, symbol)

    with _model_lock:
        model = _model_cache.get(cache_key)

    if model is None:
        model = AnalogForecastModel(
            lookback=lookback,
            horizon=horizon,
            n_neighbors=n_neighbors,
        )
        model.fit(close, ohlcv)

        with _model_lock:
            _model_cache[cache_key] = model

        logger.info(
            "Trained new model for %s/%s (rows=%d, neighbors=%d)",
            asset_type, symbol, len(close), n_neighbors,
        )

    forecast = model.predict(close, ohlcv, horizon, asset_type=asset_type)
    metrics = model.backtest(close, ohlcv, n_folds=backtest_folds)

    return forecast, metrics
