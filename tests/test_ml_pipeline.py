"""Tests for the ML pipeline: feature engineering, model training, and prediction."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

import backend.ml.service as ml_service
from backend.ml.features import FEATURE_COLUMNS, compute_features
from backend.ml.model import AnalogForecastModel, ForecastResult


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
    df = _synthetic_ohlcv()
    features = compute_features(df)

    for col in FEATURE_COLUMNS:
        assert col in features.columns, f"Missing column: {col}"

    assert not features.empty
    assert features["rsi_14"].between(0.0, 100.0).all()


def test_compute_features_drops_warmup_instead_of_forward_filling() -> None:
    df = _synthetic_ohlcv()
    features = compute_features(df)

    assert features.index[0] == df.index[50]
    assert not (features.iloc[0] == features.iloc[1]).all()


def test_analog_model_fit_predict_roundtrip() -> None:
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
    short_df = _synthetic_ohlcv(rows=50)
    close = short_df["Close"]

    model = AnalogForecastModel(lookback=45, horizon=5, n_neighbors=15)

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        with pytest.raises(ValueError):
            model.fit(close, ohlcv=short_df)


def test_predict_rejects_requested_horizon_above_trained_horizon() -> None:
    df = _synthetic_ohlcv(rows=260)
    close = df["Close"]
    model = AnalogForecastModel(lookback=45, horizon=7, n_neighbors=15)
    model.fit(close, ohlcv=df)

    with np.testing.assert_raises(ValueError):
        model.predict(close, ohlcv=df, horizon=30, asset_type="stock")


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


def test_train_and_predict_cache_invalidates_when_latest_observation_changes(monkeypatch) -> None:
    df = _synthetic_ohlcv(rows=260)
    close = df["Close"]
    backtest_calls = 0
    original_backtest = AnalogForecastModel.backtest

    def counted_backtest(self, close_series, ohlcv, n_folds=5):
        nonlocal backtest_calls
        backtest_calls += 1
        return original_backtest(self, close_series, ohlcv, n_folds=n_folds)

    monkeypatch.setattr(AnalogForecastModel, "backtest", counted_backtest)

    mutated_close = close.copy()
    mutated_close.iloc[-1] = mutated_close.iloc[-1] + 5.0

    with ml_service._model_lock:
        ml_service._model_cache.clear()

    try:
        ml_service.train_and_predict(
            symbol="AAPL",
            close=close,
            horizon=7,
            asset_type="stock",
            ohlcv=df,
            n_neighbors=15,
            lookback=45,
            backtest_folds=2,
        )
        ml_service.train_and_predict(
            symbol="AAPL",
            close=mutated_close,
            horizon=7,
            asset_type="stock",
            ohlcv=df.assign(Close=mutated_close),
            n_neighbors=15,
            lookback=45,
            backtest_folds=2,
        )
    finally:
        with ml_service._model_lock:
            ml_service._model_cache.clear()

    assert backtest_calls == 2


def test_backtest_uses_per_point_mape_denominator(monkeypatch) -> None:
    close = pd.Series(np.linspace(100.0, 159.0, 60), index=pd.bdate_range("2024-01-02", periods=60))
    model = AnalogForecastModel(lookback=3, horizon=2, n_neighbors=1)

    def fake_fit(self, close_series, ohlcv=None):
        self._fitted = True

    def fake_predict(self, train_close, ohlcv, horizon, asset_type="stock"):
        actual = close.iloc[len(train_close):len(train_close) + horizon].to_numpy(dtype=np.float64)
        predicted = np.array([actual[0] * 1.10, actual[1] * 0.90], dtype=np.float64)
        return ForecastResult(
            dates=["2024-04-01", "2024-04-02"],
            predicted=predicted,
            lower=predicted - 1.0,
            upper=predicted + 1.0,
            neighbors_used=1,
        )

    monkeypatch.setattr(AnalogForecastModel, "fit", fake_fit)
    monkeypatch.setattr(AnalogForecastModel, "predict", fake_predict)

    metrics = model.backtest(close, ohlcv=None, n_folds=1)

    assert metrics.mape == 10.0


def test_backtest_directional_accuracy_is_path_aware(monkeypatch) -> None:
    values = np.linspace(100.0, 160.0, 60)
    values[-3:] = [120.0, 130.0, 110.0]
    close = pd.Series(values, index=pd.bdate_range("2024-01-02", periods=60))
    model = AnalogForecastModel(lookback=3, horizon=3, n_neighbors=1)

    def fake_fit(self, close_series, ohlcv=None):
        self._fitted = True

    def fake_predict(self, train_close, ohlcv, horizon, asset_type="stock"):
        predicted = np.array([125.0, 115.0, 105.0], dtype=np.float64)
        return ForecastResult(
            dates=["2024-04-01", "2024-04-02", "2024-04-03"],
            predicted=predicted,
            lower=predicted - 1.0,
            upper=predicted + 1.0,
            neighbors_used=1,
        )

    monkeypatch.setattr(AnalogForecastModel, "fit", fake_fit)
    monkeypatch.setattr(AnalogForecastModel, "predict", fake_predict)

    metrics = model.backtest(close, ohlcv=None, n_folds=1)

    assert metrics.directional_accuracy == 0.5
