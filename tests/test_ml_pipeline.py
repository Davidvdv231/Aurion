"""Tests for the ML pipeline: feature engineering, model training, and prediction."""
from __future__ import annotations

import numpy as np
import pandas as pd

import backend.ml.service as ml_service
from backend.ml.features import FEATURE_COLUMNS, compute_features
from backend.ml.model import AnalogForecastModel


def _synthetic_ohlcv(rows: int = 240) -> pd.DataFrame:
    index = pd.bdate_range("2024-01-02", periods=rows)
    rng = np.random.default_rng(7)
    trend = np.linspace(100.0, 165.0, rows)
    cycle = 3.5 * np.sin(np.linspace(0.0, 8.0 * np.pi, rows))
    noise = rng.normal(0.0, 0.7, rows)
    close = trend + cycle + noise
    open_ = close + rng.normal(0.0, 0.4, rows)
    high = np.maximum(open_, close) + rng.uniform(0.2, 1.2, rows)
    low = np.minimum(open_, close) - rng.uniform(0.2, 1.2, rows)
    volume = rng.integers(900_000, 1_500_000, rows)

    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=index,
    )


def test_compute_features_produces_all_expected_columns() -> None:
    """compute_features returns all FEATURE_COLUMNS with valid ranges."""
    df = _synthetic_ohlcv()
    features = compute_features(df)

    for col in FEATURE_COLUMNS:
        assert col in features.columns, f"Missing column: {col}"

    cleaned = features.dropna()
    assert not cleaned.empty
    assert cleaned["rsi_14"].between(0.0, 100.0).all()


def test_analog_model_fit_predict_roundtrip() -> None:
    """AnalogForecastModel can fit, predict, and backtest on synthetic data."""
    df = _synthetic_ohlcv()
    close = df["Close"]

    model = AnalogForecastModel(lookback=45, horizon=5, n_neighbors=15)
    model.fit(close, ohlcv=df)

    forecast = model.predict(close, ohlcv=df, horizon=5, asset_type="stock")

    assert len(forecast.dates) == 5
    assert len(forecast.predicted) == 5
    assert len(forecast.lower) == 5
    assert len(forecast.upper) == 5
    assert forecast.neighbors_used <= 15
    assert all(forecast.lower[i] <= forecast.predicted[i] <= forecast.upper[i] for i in range(5))

    metrics = model.backtest(close, ohlcv=df, n_folds=3)

    assert metrics.mae >= 0.0
    assert metrics.rmse >= 0.0
    assert metrics.mape >= 0.0
    assert 0.0 <= metrics.directional_accuracy <= 1.0
    assert metrics.validation_windows >= 1


def test_model_rejects_insufficient_data() -> None:
    """Model raises ValueError when data is too short."""
    short_df = _synthetic_ohlcv(rows=50)
    close = short_df["Close"]

    model = AnalogForecastModel(lookback=45, horizon=5, n_neighbors=15)

    try:
        model.fit(close, ohlcv=short_df)
        assert False, "Expected ValueError for insufficient data"
    except ValueError:
        pass


def test_train_and_predict_cache_separates_models_by_horizon() -> None:
    df = _synthetic_ohlcv(rows=260)
    close = df["Close"]

    with ml_service._model_lock:
        ml_service._model_cache.clear()

    try:
        forecast_short, _ = ml_service.train_and_predict(
            symbol="AAPL",
            close=close,
            horizon=7,
            asset_type="stock",
            ohlcv=df,
            n_neighbors=15,
            lookback=45,
            backtest_folds=2,
        )
        forecast_long, _ = ml_service.train_and_predict(
            symbol="AAPL",
            close=close,
            horizon=30,
            asset_type="stock",
            ohlcv=df,
            n_neighbors=15,
            lookback=45,
            backtest_folds=2,
        )
    finally:
        with ml_service._model_lock:
            ml_service._model_cache.clear()

    assert len(forecast_short.dates) == 7
    assert len(forecast_long.dates) == 30


def test_train_and_predict_reuses_cached_backtest_metrics(monkeypatch) -> None:
    df = _synthetic_ohlcv(rows=260)
    close = df["Close"]
    backtest_calls = 0
    original_backtest = AnalogForecastModel.backtest

    def counted_backtest(self, close_series, ohlcv, n_folds=5):
        nonlocal backtest_calls
        backtest_calls += 1
        return original_backtest(self, close_series, ohlcv, n_folds=n_folds)

    monkeypatch.setattr(AnalogForecastModel, "backtest", counted_backtest)

    with ml_service._model_lock:
        ml_service._model_cache.clear()

    try:
        _, first_metrics = ml_service.train_and_predict(
            symbol="AAPL",
            close=close,
            horizon=7,
            asset_type="stock",
            ohlcv=df,
            n_neighbors=15,
            lookback=45,
            backtest_folds=2,
        )
        _, second_metrics = ml_service.train_and_predict(
            symbol="AAPL",
            close=close,
            horizon=7,
            asset_type="stock",
            ohlcv=df,
            n_neighbors=15,
            lookback=45,
            backtest_folds=2,
        )
    finally:
        with ml_service._model_lock:
            ml_service._model_cache.clear()

    assert backtest_calls == 1
    assert second_metrics == first_metrics
