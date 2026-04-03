"""Analog Pattern Forecaster - non-linear nearest-neighbor ensemble model."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.ml.features import FEATURE_COLUMNS, compute_features


@dataclass(slots=True)
class FeatureDifference:
    feature: str
    difference_score: float
    value: float
    relation: str  # "higher" | "lower" | "similar"


@dataclass(slots=True)
class ForecastResult:
    dates: list[str]
    predicted: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    neighbors_used: int
    top_features: list[FeatureDifference] = field(default_factory=list)
    avg_neighbor_distance: float = 0.0
    nearest_analog_date: str = ""


@dataclass(slots=True)
class BacktestMetrics:
    mae: float
    rmse: float
    mape: float
    directional_accuracy: float
    validation_windows: int


@dataclass
class AnalogForecastModel:
    """K-nearest-neighbor analog forecaster on normalized technical features."""

    lookback: int = 60
    horizon: int = 30
    n_neighbors: int = 24
    _feature_mean: np.ndarray = field(default_factory=lambda: np.array([]))
    _feature_std: np.ndarray = field(default_factory=lambda: np.array([]))
    _feature_raw_std: np.ndarray = field(default_factory=lambda: np.array([]))
    _windows: np.ndarray = field(default_factory=lambda: np.array([]))
    _future_returns: np.ndarray = field(default_factory=lambda: np.array([]))
    _window_end_features_raw: np.ndarray = field(default_factory=lambda: np.array([]))
    _window_end_positions: np.ndarray = field(default_factory=lambda: np.array([]))
    _fitted: bool = False

    @property
    def model_name(self) -> str:
        return f"analog-k{self.n_neighbors}-lb{self.lookback}"

    @property
    def top_k(self) -> int:
        return self.n_neighbors

    @property
    def feature_columns(self) -> list[str]:
        return list(FEATURE_COLUMNS)

    @property
    def asset_type(self) -> str:
        return "generic"

    def to_state(self) -> dict:
        return {
            "lookback": self.lookback,
            "horizon": self.horizon,
            "n_neighbors": self.n_neighbors,
            "feature_mean": self._feature_mean,
            "feature_std": self._feature_std,
            "feature_raw_std": self._feature_raw_std,
            "windows": self._windows,
            "future_returns": self._future_returns,
            "window_end_features_raw": self._window_end_features_raw,
            "window_end_positions": self._window_end_positions,
            "fitted": self._fitted,
        }

    @classmethod
    def from_state(cls, state: dict) -> "AnalogForecastModel":
        model = cls(
            lookback=int(state["lookback"]),
            horizon=int(state["horizon"]),
            n_neighbors=int(state.get("n_neighbors", state.get("top_k", 24))),
        )
        model._feature_mean = np.asarray(state["feature_mean"])
        model._feature_std = np.asarray(state["feature_std"])
        model._feature_raw_std = np.asarray(state.get("feature_raw_std", np.array([])))
        model._windows = np.asarray(state["windows"])
        model._future_returns = np.asarray(state["future_returns"])
        model._window_end_features_raw = np.asarray(state.get("window_end_features_raw", np.array([])))
        model._window_end_positions = np.asarray(state.get("window_end_positions", np.array([])))
        model._fitted = bool(state.get("fitted", True))
        return model

    def _prepare_inputs(
        self,
        close: pd.Series,
        ohlcv: pd.DataFrame | None,
    ) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
        if ohlcv is not None and "Close" in ohlcv.columns:
            df = ohlcv
        else:
            df = pd.DataFrame({"Close": close})

        features = compute_features(df)
        feat_matrix = features[FEATURE_COLUMNS].to_numpy(dtype=np.float64)
        feat_matrix = np.nan_to_num(feat_matrix, nan=0.0, posinf=0.0, neginf=0.0)
        aligned_close = df["Close"].astype(float).reindex(features.index)
        close_arr = aligned_close.to_numpy(dtype=np.float64)
        return features, feat_matrix, close_arr

    def fit(self, close: pd.Series, ohlcv: pd.DataFrame | None = None) -> None:
        features, feat_matrix, close_arr = self._prepare_inputs(close, ohlcv)
        if len(features) <= self.lookback + self.horizon:
            raise ValueError("Insufficient data to fit model")

        self._feature_mean = np.nanmean(feat_matrix, axis=0)
        self._feature_std = np.nanstd(feat_matrix, axis=0)
        self._feature_std[self._feature_std < 1e-8] = 1.0
        self._feature_raw_std = np.nanstd(feat_matrix, axis=0)
        self._feature_raw_std[self._feature_raw_std < 1e-8] = 1.0

        normalized = (feat_matrix - self._feature_mean) / self._feature_std

        windows: list[np.ndarray] = []
        future_returns: list[np.ndarray] = []
        window_end_features_raw: list[np.ndarray] = []
        window_end_positions: list[int] = []
        n = len(normalized)

        for i in range(self.lookback, n - self.horizon):
            window = normalized[i - self.lookback:i]
            if np.any(np.isnan(window)):
                continue

            base_price = close_arr[i - 1]
            if base_price <= 0:
                continue

            future_prices = close_arr[i:i + self.horizon]
            if len(future_prices) < self.horizon:
                continue

            windows.append(window.flatten())
            future_returns.append(future_prices / base_price - 1.0)
            window_end_features_raw.append(feat_matrix[i - 1].copy())
            window_end_positions.append(i - 1)

        if not windows:
            raise ValueError("Insufficient data to fit model")

        self._windows = np.array(windows)
        self._future_returns = np.array(future_returns)
        self._window_end_features_raw = np.array(window_end_features_raw)
        self._window_end_positions = np.array(window_end_positions, dtype=np.int64)
        self._fitted = True

    def predict(
        self,
        close: pd.Series,
        ohlcv: pd.DataFrame | None,
        horizon: int,
        asset_type: str = "stock",
    ) -> ForecastResult:
        if not self._fitted:
            raise RuntimeError("Model not fitted")
        if horizon != self.horizon:
            raise ValueError(f"Requested horizon {horizon} exceeds trained horizon {self.horizon}")

        features, feat_matrix, _ = self._prepare_inputs(close, ohlcv)
        if len(features) < self.lookback:
            raise ValueError("Insufficient data to build prediction window")

        normalized = (feat_matrix - self._feature_mean) / self._feature_std
        query = normalized[-self.lookback:].flatten()

        diffs = self._windows - query
        distances = np.sqrt(np.sum(diffs ** 2, axis=1))
        k = min(self.n_neighbors, len(distances))
        nearest_idx = np.argpartition(distances, k - 1)[:k]
        nearest_distances = distances[nearest_idx]
        nearest_returns = self._future_returns[nearest_idx]

        min_dist = np.min(nearest_distances)
        epsilon = max(min_dist * 0.01, 1e-6)
        weights = 1.0 / (nearest_distances + epsilon)
        weights /= weights.sum()

        query_features_raw = feat_matrix[-1]
        weighted_neighbor_features = np.average(
            self._window_end_features_raw[nearest_idx],
            axis=0,
            weights=weights,
        )
        feature_deltas = query_features_raw - weighted_neighbor_features
        standardized_deltas = feature_deltas / self._feature_raw_std
        abs_deltas = np.abs(standardized_deltas)
        top_5_idx = np.argsort(abs_deltas)[::-1][:5]
        avg_neighbor_distance = float(np.average(nearest_distances, weights=weights))

        top_features: list[FeatureDifference] = []
        for fi in top_5_idx:
            delta = float(feature_deltas[fi])
            raw_value = float(query_features_raw[fi])
            similar_threshold = max(float(self._feature_raw_std[fi]) * 0.25, 1e-6)
            if abs(delta) < similar_threshold:
                relation = "similar"
            elif delta > 0:
                relation = "higher"
            else:
                relation = "lower"
            top_features.append(
                FeatureDifference(
                    feature=FEATURE_COLUMNS[fi],
                    difference_score=round(float(abs_deltas[fi]), 4),
                    value=round(raw_value, 4),
                    relation=relation,
                )
            )

        best_neighbor_idx = nearest_idx[np.argmin(nearest_distances)]
        nearest_analog_date = ""
        try:
            analog_position = int(self._window_end_positions[best_neighbor_idx])
            if analog_position < len(features.index):
                nearest_analog_date = str(features.index[analog_position].date())
        except Exception:
            pass

        if nearest_returns.shape[1] != horizon:
            raise ValueError(
                f"Requested horizon {horizon} exceeds trained horizon {nearest_returns.shape[1]}"
            )

        weighted_returns = np.average(nearest_returns, axis=0, weights=weights)
        lower_returns = np.array([
            _weighted_quantile(nearest_returns[:, t], weights, 0.10)
            for t in range(horizon)
        ])
        upper_returns = np.array([
            _weighted_quantile(nearest_returns[:, t], weights, 0.90)
            for t in range(horizon)
        ])

        base_price = float(close.iloc[-1])
        predicted = base_price * (1.0 + weighted_returns)
        lower = base_price * (1.0 + lower_returns)
        upper = base_price * (1.0 + upper_returns)

        last_date = close.index[-1]
        if asset_type == "crypto":
            dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon, freq="D")
        else:
            dates = pd.bdate_range(last_date + pd.Timedelta(days=1), periods=horizon)

        return ForecastResult(
            dates=[d.date().isoformat() for d in dates],
            predicted=predicted,
            lower=lower,
            upper=upper,
            neighbors_used=k,
            top_features=top_features,
            avg_neighbor_distance=round(avg_neighbor_distance, 4),
            nearest_analog_date=nearest_analog_date,
        )

    def backtest(self, close: pd.Series, ohlcv: pd.DataFrame | None, n_folds: int = 5) -> BacktestMetrics:
        if ohlcv is not None and "Close" in ohlcv.columns:
            df = ohlcv
        else:
            df = pd.DataFrame({"Close": close})

        n = len(close)
        min_train = self.lookback + self.horizon + 50
        fold_size = max(self.horizon, (n - min_train) // max(n_folds, 1))

        all_errors: list[float] = []
        all_actuals: list[float] = []
        fold_direction_scores: list[float] = []

        for fold in range(n_folds):
            test_end = n - (fold * fold_size)
            test_start = test_end - self.horizon
            train_end = test_start
            if train_end < min_train:
                break

            train_close = close.iloc[:train_end]
            train_ohlcv = df.iloc[:train_end] if ohlcv is not None else None
            fold_model = AnalogForecastModel(
                lookback=self.lookback,
                horizon=self.horizon,
                n_neighbors=self.n_neighbors,
            )

            try:
                fold_model.fit(train_close, train_ohlcv)
                result = fold_model.predict(train_close, train_ohlcv, self.horizon)
            except (ValueError, RuntimeError):
                continue

            actual = close.iloc[test_start:test_end].to_numpy(dtype=np.float64)
            actual_len = min(len(actual), len(result.predicted))
            if actual_len == 0:
                continue

            pred = result.predicted[:actual_len]
            act = actual[:actual_len]
            errors = np.abs(pred - act)
            all_errors.extend(errors.tolist())
            all_actuals.extend(np.abs(act).tolist())

            if actual_len > 1:
                pred_steps = np.sign(np.diff(pred))
                actual_steps = np.sign(np.diff(act))
                fold_direction_scores.append(float(np.mean(pred_steps == actual_steps)))

        if not all_errors:
            return BacktestMetrics(mae=0, rmse=0, mape=0, directional_accuracy=0.5, validation_windows=0)

        errors_arr = np.array(all_errors, dtype=np.float64)
        actual_arr = np.array(all_actuals, dtype=np.float64)
        mae = float(np.mean(errors_arr))
        rmse = float(np.sqrt(np.mean(errors_arr ** 2)))
        mape = float(np.mean(errors_arr / np.maximum(actual_arr, 0.01))) * 100
        dir_acc = float(np.mean(fold_direction_scores)) if fold_direction_scores else 0.5

        return BacktestMetrics(
            mae=round(mae, 4),
            rmse=round(rmse, 4),
            mape=round(mape, 2),
            directional_accuracy=round(dir_acc, 4),
            validation_windows=len(fold_direction_scores),
        )


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    sorted_idx = np.argsort(values)
    sorted_vals = values[sorted_idx]
    sorted_weights = weights[sorted_idx]
    cumulative = np.cumsum(sorted_weights)
    cutoff = quantile * cumulative[-1]
    idx = np.searchsorted(cumulative, cutoff)
    idx = min(idx, len(sorted_vals) - 1)
    return float(sorted_vals[idx])
