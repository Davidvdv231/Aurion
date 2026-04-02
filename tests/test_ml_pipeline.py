from __future__ import annotations

from pathlib import Path
import uuid

import numpy as np
import pandas as pd

from backend.ml.baseline import build_statistical_baseline
from backend.ml.features import build_feature_frame
from backend.ml.service import load_latest_model, train_and_validate_model


ROOT = Path(__file__).resolve().parents[1]


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
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=index,
    )


def test_feature_engineering_produces_core_indicators() -> None:
    frame = build_feature_frame(_synthetic_ohlcv())

    for column in (
        "rsi_14",
        "macd",
        "macd_signal",
        "bollinger_upper_20",
        "bollinger_lower_20",
        "volume_zscore_20",
        "momentum_10",
    ):
        assert column in frame.columns

    cleaned = frame.dropna()
    assert not cleaned.empty
    assert cleaned["rsi_14"].between(0.0, 100.0).all()


def test_end_to_end_forecast_backtest_and_registry_roundtrip() -> None:
    ohlcv = _synthetic_ohlcv()

    scratch_root = ROOT / ".tmp" / "ml-tests"
    scratch_root.mkdir(parents=True, exist_ok=True)
    temp_dir = scratch_root / f"case-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)

    result = train_and_validate_model(
        ohlcv,
        asset_type="stock",
        lookback=45,
        horizon=5,
        top_k=15,
        registry_root=temp_dir,
        persist=True,
    )

    assert result.artifact is not None
    assert result.backtest is not None
    assert result.backtest.folds
    assert result.backtest.metrics["overall_mae"] >= 0.0
    assert 0.0 <= result.validation["directional_accuracy"] <= 1.0

    forecast = result.model.predict(ohlcv, asset_type="stock")
    baseline = build_statistical_baseline(ohlcv["close"], horizon=5, asset_type="stock")
    assert len(forecast.path) == 5
    assert forecast.path[0].lower <= forecast.path[0].predicted <= forecast.path[0].upper
    assert 0.0 <= forecast.summary["confidence"] <= 1.0
    assert forecast.summary["trend"] in {"bullish", "bearish", "neutral"}
    assert forecast.summary["signal"] in {"buy", "hold", "sell"}
    assert any(
        abs(model_point.predicted - baseline_point.predicted) > 0.25
        for model_point, baseline_point in zip(forecast.path, baseline.path)
    )

    loaded = load_latest_model(registry_root=temp_dir)
    loaded_forecast = loaded.predict(ohlcv, asset_type="stock")
    assert len(loaded_forecast.path) == 5
    assert loaded_forecast.summary["trend"] == forecast.summary["trend"]
