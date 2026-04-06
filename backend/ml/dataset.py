from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(slots=True)
class SupervisedDataset:
    X: np.ndarray
    y: np.ndarray
    anchors: pd.Index
    anchor_closes: np.ndarray
    feature_columns: tuple[str, ...]
    lookback: int
    horizon: int


def split_train_validation_test(
    frame: pd.DataFrame,
    validation_size: float = 0.15,
    test_size: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if not 0.0 < validation_size < 1.0 or not 0.0 < test_size < 1.0:
        raise ValueError("validation_size and test_size must be in (0, 1).")
    if validation_size + test_size >= 1.0:
        raise ValueError("validation_size + test_size must be smaller than 1.")

    n_rows = len(frame)
    test_start = int(round(n_rows * (1.0 - test_size)))
    val_start = int(round(n_rows * (1.0 - test_size - validation_size)))
    return (
        frame.iloc[:val_start].copy(),
        frame.iloc[val_start:test_start].copy(),
        frame.iloc[test_start:].copy(),
    )


def build_supervised_dataset(
    feature_frame: pd.DataFrame,
    lookback: int,
    horizon: int,
    feature_columns: tuple[str, ...] | None = None,
) -> SupervisedDataset:
    if lookback < 2:
        raise ValueError("lookback must be at least 2.")
    if horizon < 1:
        raise ValueError("horizon must be at least 1.")
    if "close" not in feature_frame.columns:
        raise ValueError("feature_frame must contain a close column.")

    feature_columns = feature_columns or tuple(
        column for column in feature_frame.columns if column != "close"
    )
    frame = feature_frame[list(feature_columns) + ["close"]].dropna().copy()
    if len(frame) < lookback + horizon:
        raise ValueError("Not enough rows to build a supervised dataset.")

    x_rows: list[np.ndarray] = []
    y_rows: list[np.ndarray] = []
    anchors: list[pd.Timestamp] = []
    anchor_closes: list[float] = []

    for end_idx in range(lookback - 1, len(frame) - horizon):
        window = frame.iloc[end_idx - lookback + 1 : end_idx + 1]
        future = frame["close"].iloc[end_idx + 1 : end_idx + 1 + horizon].to_numpy(dtype=float)
        anchor_close = float(frame["close"].iloc[end_idx])
        if anchor_close <= 0.0:
            continue
        x_rows.append(window[list(feature_columns)].to_numpy(dtype=float).reshape(-1))
        y_rows.append((future / anchor_close) - 1.0)
        anchors.append(frame.index[end_idx])
        anchor_closes.append(anchor_close)

    if not x_rows:
        raise ValueError("Not enough valid rows to build a supervised dataset.")

    return SupervisedDataset(
        X=np.vstack(x_rows),
        y=np.vstack(y_rows),
        anchors=pd.Index(anchors),
        anchor_closes=np.asarray(anchor_closes, dtype=float),
        feature_columns=tuple(feature_columns),
        lookback=lookback,
        horizon=horizon,
    )
