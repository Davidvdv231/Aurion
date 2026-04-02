from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from backend.ml.backtest import BacktestResult, walk_forward_backtest
from backend.ml.baseline import BaselineForecast, build_statistical_baseline
from backend.ml.model import AnalogForecastModel, ForecastOutput
from backend.ml.registry import ModelArtifact, ModelRegistry


@dataclass(slots=True)
class ForecastServiceResult:
    model: AnalogForecastModel
    artifact: ModelArtifact | None
    backtest: BacktestResult | None
    validation: dict[str, float] | None


def _default_model_factory(lookback: int, horizon: int, top_k: int, asset_type: str) -> AnalogForecastModel:
    return AnalogForecastModel(lookback=lookback, horizon=horizon, top_k=top_k, asset_type=asset_type)


def train_and_validate_model(
    ohlcv: pd.DataFrame,
    *,
    asset_type: Literal["stock", "crypto"] = "stock",
    lookback: int = 60,
    horizon: int = 5,
    top_k: int = 25,
    registry_root: Path | str | None = None,
    persist: bool = True,
) -> ForecastServiceResult:
    model = _default_model_factory(lookback, horizon, top_k, asset_type)
    model.fit(ohlcv, asset_type=asset_type)

    backtest = walk_forward_backtest(
        ohlcv,
        model_factory=lambda: _default_model_factory(lookback, horizon, top_k, asset_type),
        min_train_size=max(lookback + horizon, 120),
        step=max(1, horizon),
        max_folds=5,
    )
    validation = dict(backtest.metrics)
    artifact = None
    if persist:
        registry = ModelRegistry(registry_root)
        artifact = registry.save(model, metadata={"backtest_metrics": backtest.metrics})

    return ForecastServiceResult(model=model, artifact=artifact, backtest=backtest, validation=validation)


def load_latest_model(
    model_name: str = "analog_forecaster",
    registry_root: Path | str | None = None,
) -> AnalogForecastModel:
    registry = ModelRegistry(registry_root)
    return registry.load_latest(model_name)


def predict_asset(
    ohlcv: pd.DataFrame,
    *,
    asset_type: Literal["stock", "crypto"] = "stock",
    lookback: int = 60,
    horizon: int = 5,
    top_k: int = 25,
) -> tuple[AnalogForecastModel, ForecastOutput, BaselineForecast]:
    model = _default_model_factory(lookback, horizon, top_k, asset_type)
    model.fit(ohlcv, asset_type=asset_type)
    forecast = model.predict(ohlcv, asset_type=asset_type)
    baseline = build_statistical_baseline(ohlcv["close"], horizon=horizon, asset_type=asset_type)
    return model, forecast, baseline
