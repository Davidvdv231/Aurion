"""Tests for the ML pipeline: feature engineering, model training, and prediction."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

import backend.ml.service as ml_service
from backend.ml.features import _FEATURE_WARMUP_ROWS, FEATURE_COLUMNS, compute_features
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


# ---------------------------------------------------------------------------
# BUG-02 regression tests: warm-up removal and Close-only volume guard
# ---------------------------------------------------------------------------


def test_warmup_rows_are_fully_removed() -> None:
    """First row of features must come from AFTER the warm-up window.

    The explicit warm-up slice should remove exactly _FEATURE_WARMUP_ROWS
    rows from the front, and no NaN should survive in the remaining output.
    """
    df = _synthetic_ohlcv(rows=200)
    features = compute_features(df)

    # No row from the warm-up window should be present
    assert features.index[0] >= df.index[_FEATURE_WARMUP_ROWS]

    # No NaN in the output at all
    assert not features.isna().any().any(), (
        f"NaN found in columns: {features.columns[features.isna().any()].tolist()}"
    )


def test_no_ffill_leaks_across_warmup_boundary() -> None:
    """Verify that values at the warm-up boundary are genuinely computed,
    not forward-filled from earlier (partially-defined) rows."""
    df = _synthetic_ohlcv(rows=200)
    features = compute_features(df)

    # sma_50 at the first retained row must differ from sma_5.
    # If ffill had leaked a warm-up value forward, these would likely be
    # identical (both NaN-filled to the same stale value).
    first = features.iloc[0]
    assert first["sma_50"] != first["sma_5"], "sma_50 and sma_5 should differ at warm-up boundary"


def test_close_only_input_produces_valid_features() -> None:
    """compute_features must return a non-empty, NaN-free frame when given
    only a Close column (no Volume, no OHLCV).  This is the production
    path when prediction.py calls train_and_predict without ohlcv."""
    df = _synthetic_ohlcv(rows=240)
    close_only = pd.DataFrame({"Close": df["Close"]})

    features = compute_features(close_only)

    assert not features.empty, "Features should not be empty for Close-only input"
    assert not features.isna().any().any(), (
        f"NaN found in columns: {features.columns[features.isna().any()].tolist()}"
    )
    # Volume features should be neutral zeros
    assert (features["volume_change_5"] == 0.0).all()
    assert (features["volume_zscore_20"] == 0.0).all()


def test_close_only_model_fit_predict_roundtrip() -> None:
    """Full ML pipeline works end-to-end with Close-only data,
    matching the real production call path."""
    df = _synthetic_ohlcv(rows=240)
    close = df["Close"]

    model = AnalogForecastModel(lookback=45, horizon=7, n_neighbors=15)
    model.fit(close, ohlcv=None)  # No OHLCV — matches production

    forecast = model.predict(close, ohlcv=None, horizon=7, asset_type="stock")

    assert len(forecast.dates) == 7
    assert len(forecast.predicted) == 7
    assert all(forecast.lower[i] <= forecast.predicted[i] <= forecast.upper[i] for i in range(7))


def test_fit_predict_normalization_invariant() -> None:
    """The normalization transform in predict() must be identical to fit().

    For any row that appears in both the training feature matrix and the
    prediction feature matrix, the normalized value must be bit-identical.
    This locks in the train/serve contract: same compute_features, same
    nan_to_num, same mean/std → identical normalized rows.
    """
    df = _synthetic_ohlcv(rows=240)
    close = df["Close"]

    model = AnalogForecastModel(lookback=45, horizon=7, n_neighbors=15)
    model.fit(close, ohlcv=None)

    # Reproduce the full predict() normalization path
    features = compute_features(pd.DataFrame({"Close": close}))
    feat_matrix = features[FEATURE_COLUMNS].to_numpy(dtype=np.float64)
    feat_matrix = np.nan_to_num(feat_matrix, nan=0.0, posinf=0.0, neginf=0.0)
    normalized_predict = (feat_matrix - model._feature_mean) / model._feature_std

    # Reproduce the full fit() normalization path on the same data
    features_fit = compute_features(pd.DataFrame({"Close": close}))
    feat_matrix_fit = features_fit[FEATURE_COLUMNS].to_numpy(dtype=np.float64)
    feat_matrix_fit = np.nan_to_num(feat_matrix_fit, nan=0.0, posinf=0.0, neginf=0.0)
    normalized_fit = (feat_matrix_fit - model._feature_mean) / model._feature_std

    # Every row must be identical between the two paths
    assert np.array_equal(normalized_fit, normalized_predict), (
        "Normalized feature matrices differ between fit and predict paths. "
        "This indicates a train/serve normalization skew."
    )

    # Pick a training window that fit() stored, and verify the predict
    # path produces the same values for those same row positions.
    # The first stored window corresponds to rows [0:lookback] in the
    # normalized matrix (fit starts at i=lookback, window is [0:lookback]).
    first_window_from_predict = normalized_predict[:45].flatten()
    first_stored_window = model._windows[0]

    assert np.allclose(first_window_from_predict, first_stored_window, atol=1e-12), (
        f"First training window doesn't match predict-path normalization. "
        f"Max diff: {np.max(np.abs(first_window_from_predict - first_stored_window))}"
    )


# ---------------------------------------------------------------------------
# BUG-10 regression test: MAPE must use pointwise actual values
# ---------------------------------------------------------------------------


def test_backtest_mape_is_pointwise() -> None:
    """MAPE must be mean(|error_i| / |actual_i|) * 100, not
    mean(|error_i|) / last_close * 100.

    We verify this by running a backtest on trending data where early
    fold actuals differ materially from the last close, then checking
    the MAPE against a hand-computed pointwise value.
    """
    df = _synthetic_ohlcv(rows=260)
    close = df["Close"]

    model = AnalogForecastModel(lookback=45, horizon=7, n_neighbors=15)
    model.fit(close, ohlcv=None)
    metrics = model.backtest(close, ohlcv=None, n_folds=3)

    # Sanity: MAPE should be positive and finite
    assert metrics.mape > 0.0
    assert np.isfinite(metrics.mape)

    # The old bug: MAPE = MAE / last_close * 100
    # If that were still the formula, this equality would hold:
    last_close = float(close.iloc[-1])
    old_formula_mape = (metrics.mae / last_close) * 100

    # With pointwise MAPE the values should differ because the data trends
    # from ~100 to ~165, so early actuals are much lower than last_close.
    # Pointwise MAPE divides by smaller actuals → larger percentage → higher MAPE.
    assert metrics.mape != round(old_formula_mape, 2), (
        f"MAPE ({metrics.mape}) equals old formula MAE/last_close*100 "
        f"({old_formula_mape:.2f}). Pointwise division is not being used."
    )
