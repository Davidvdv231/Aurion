from __future__ import annotations

from backend.ml.backtest import BacktestResult, walk_forward_backtest
from backend.ml.baseline import BaselineForecast, build_statistical_baseline
from backend.ml.dataset import SupervisedDataset, build_supervised_dataset, split_train_validation_test
from backend.ml.features import FEATURE_COLUMNS, FeatureFrameConfig, build_feature_frame
from backend.ml.metrics import directional_accuracy, mae, mape, rmse
from backend.ml.model import AnalogForecastModel, ForecastOutput, ForecastPoint
from backend.ml.registry import ModelArtifact, ModelRegistry
from backend.ml.service import (
    ForecastServiceResult,
    load_latest_model,
    predict_asset,
    train_and_validate_model,
)

__all__ = [
    "AnalogForecastModel",
    "BacktestResult",
    "BaselineForecast",
    "FEATURE_COLUMNS",
    "FeatureFrameConfig",
    "ForecastOutput",
    "ForecastPoint",
    "ForecastServiceResult",
    "ModelArtifact",
    "ModelRegistry",
    "SupervisedDataset",
    "build_feature_frame",
    "build_statistical_baseline",
    "build_supervised_dataset",
    "directional_accuracy",
    "load_latest_model",
    "mae",
    "mape",
    "predict_asset",
    "rmse",
    "split_train_validation_test",
    "train_and_validate_model",
    "walk_forward_backtest",
]
