"""High-level ML service: train, cache, and predict."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from threading import Lock

import pandas as pd

from backend.ml.model import AnalogForecastModel, BacktestMetrics, ForecastResult
from backend.ticker_catalog import AssetType

logger = logging.getLogger("stock_predictor.ml")

# In-memory model cache with LRU eviction and TTL
_MAX_CACHE_SIZE = 50
_MODEL_TTL_SECONDS = 3600  # 1 hour

_CacheKey = tuple[str, str, int, int, int, int, bool, str]
_CacheEntry = tuple[AnalogForecastModel, BacktestMetrics, float]  # (model, metrics, created_at)
_model_cache: OrderedDict[_CacheKey, _CacheEntry] = OrderedDict()
_model_lock = Lock()

MIN_HISTORY_ROWS = 180


def _cache_get(key: _CacheKey) -> tuple[AnalogForecastModel, BacktestMetrics] | None:
    """Get a cached model and backtest metrics if they haven't expired."""
    with _model_lock:
        entry = _model_cache.get(key)
        if entry is None:
            return None
        model, metrics, created_at = entry
        if time.monotonic() - created_at > _MODEL_TTL_SECONDS:
            _model_cache.pop(key, None)
            logger.info("Cache expired for %s", key)
            return None
        _model_cache.move_to_end(key)
        return model, metrics


def _cache_put(key: _CacheKey, model: AnalogForecastModel, metrics: BacktestMetrics) -> None:
    """Store a model and its backtest metrics in cache."""
    with _model_lock:
        _model_cache[key] = (model, metrics, time.monotonic())
        _model_cache.move_to_end(key)
        while len(_model_cache) > _MAX_CACHE_SIZE:
            evicted_key, _ = _model_cache.popitem(last=False)
            logger.info("Evicted cached model for %s (LRU)", evicted_key)


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
        raise ValueError(f"Need at least {MIN_HISTORY_ROWS} data points, got {len(close)}")

    use_ohlcv = ohlcv is not None and "Close" in ohlcv.columns
    cache_key = (
        asset_type,
        symbol,
        horizon,
        n_neighbors,
        lookback,
        backtest_folds,
        use_ohlcv,
        f"{pd.Timestamp(close.index[-1]).isoformat()}:{float(close.iloc[-1]):.6f}",
    )
    cached_entry = _cache_get(cache_key)

    if cached_entry is None:
        model = AnalogForecastModel(
            lookback=lookback,
            horizon=horizon,
            n_neighbors=n_neighbors,
        )
        model.fit(close, ohlcv)
        metrics = model.backtest(close, ohlcv, n_folds=backtest_folds)
        _cache_put(cache_key, model, metrics)

        logger.info(
            "Trained new model for %s/%s (rows=%d, horizon=%d, neighbors=%d, lookback=%d, folds=%d, ohlcv=%s)",
            asset_type,
            symbol,
            len(close),
            horizon,
            n_neighbors,
            lookback,
            backtest_folds,
            use_ohlcv,
        )
    else:
        model, metrics = cached_entry
        logger.info("Cache hit for %s", cache_key)

    forecast = model.predict(close, ohlcv, horizon, asset_type=asset_type)

    return forecast, metrics
