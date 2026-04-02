"""Analog Pattern Forecaster - non-linear nearest-neighbor ensemble model."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.ml.features import FEATURE_COLUMNS, compute_features


@dataclass(slots=True)
class ForecastResult:
    dates: list[str]
    predicted: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    neighbors_used: int


@dataclass(slots=True)
class BacktestMetrics:
    mae: float
    rmse: float
    mape: float
    directional_accuracy: float
    validation_windows: int


@dataclass
class AnalogForecastModel:
    """K-nearest-neighbor analog forecaster on normalized technical features.

    For each prediction, the model:
    1. Computes a feature vector for the current lookback window
    2. Finds the K most similar historical windows (weighted Euclidean distance)
    3. Generates a weighted forecast from those analogs' actual future returns
    4. Produces confidence bands from weighted quantiles
    """

    lookback: int = 60
    horizon: int = 30
    n_neighbors: int = 24
    _feature_mean: np.ndarray = field(default_factory=lambda: np.array([]))
    _feature_std: np.ndarray = field(default_factory=lambda: np.array([]))
    _windows: np.ndarray = field(default_factory=lambda: np.array([]))
    _future_returns: np.ndarray = field(default_factory=lambda: np.array([]))
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
        """Serialize model state for persistence."""
        return {
            "lookback": self.lookback,
            "horizon": self.horizon,
            "n_neighbors": self.n_neighbors,
            "feature_mean": self._feature_mean,
            "feature_std": self._feature_std,
            "windows": self._windows,
            "future_returns": self._future_returns,
            "fitted": self._fitted,
        }

    @classmethod
    def from_state(cls, state: dict) -> "AnalogForecastModel":
        """Restore a model from serialized state."""
        model = cls(
            lookback=int(state["lookback"]),
            horizon=int(state["horizon"]),
            n_neighbors=int(state.get("n_neighbors", state.get("top_k", 24))),
        )
        model._feature_mean = np.asarray(state["feature_mean"])
        model._feature_std = np.asarray(state["feature_std"])
        model._windows = np.asarray(state["windows"])
        model._future_returns = np.asarray(state["future_returns"])
        model._fitted = bool(state.get("fitted", True))
        return model

    def fit(self, close: pd.Series, ohlcv: pd.DataFrame | None = None) -> None:
        """Fit the model on historical data."""
        if ohlcv is not None and "Close" in ohlcv.columns:
            df = ohlcv
        else:
            df = pd.DataFrame({"Close": close})

        features = compute_features(df)
        feat_matrix = features[FEATURE_COLUMNS].to_numpy(dtype=np.float64)
        close_arr = close.to_numpy(dtype=np.float64)

        # Replace NaN/inf with 0 for normalization
        feat_matrix = np.nan_to_num(feat_matrix, nan=0.0, posinf=0.0, neginf=0.0)

        # Compute normalization statistics (excluding initial NaN rows)
        valid_start = self.lookback
        valid_features = feat_matrix[valid_start:]
        self._feature_mean = np.nanmean(valid_features, axis=0)
        self._feature_std = np.nanstd(valid_features, axis=0)
        self._feature_std[self._feature_std < 1e-8] = 1.0

        # Normalize
        normalized = (feat_matrix - self._feature_mean) / self._feature_std

        # Build windows and future returns
        windows = []
        future_returns = []
        n = len(normalized)

        for i in range(self.lookback, n - self.horizon):
            window = normalized[i - self.lookback: i]
            if np.any(np.isnan(window)):
                continue

            base_price = close_arr[i - 1]
            if base_price <= 0:
                continue

            future_prices = close_arr[i: i + self.horizon]
            if len(future_prices) < self.horizon:
                continue

            returns = future_prices / base_price - 1.0
            windows.append(window.flatten())
            future_returns.append(returns)

        if not windows:
            raise ValueError("Insufficient data to fit model")

        self._windows = np.array(windows)
        self._future_returns = np.array(future_returns)
        self._fitted = True

    def predict(
        self,
        close: pd.Series,
        ohlcv: pd.DataFrame | None,
        horizon: int,
        asset_type: str = "stock",
    ) -> ForecastResult:
        """Generate a forecast from the current market state."""
        if not self._fitted:
            raise RuntimeError("Model not fitted")

        if ohlcv is not None and "Close" in ohlcv.columns:
            df = ohlcv
        else:
            df = pd.DataFrame({"Close": close})

        features = compute_features(df)
        feat_matrix = features[FEATURE_COLUMNS].to_numpy(dtype=np.float64)
        feat_matrix = np.nan_to_num(feat_matrix, nan=0.0, posinf=0.0, neginf=0.0)

        normalized = (feat_matrix - self._feature_mean) / self._feature_std
        query = normalized[-self.lookback:].flatten()

        # Compute weighted distances to all stored windows
        diffs = self._windows - query
        distances = np.sqrt(np.sum(diffs ** 2, axis=1))

        # Select K nearest neighbors
        k = min(self.n_neighbors, len(distances))
        nearest_idx = np.argpartition(distances, k)[:k]
        nearest_distances = distances[nearest_idx]
        nearest_returns = self._future_returns[nearest_idx]

        # Inverse-distance weighting (avoid division by zero)
        min_dist = np.min(nearest_distances)
        epsilon = max(min_dist * 0.01, 1e-6)
        weights = 1.0 / (nearest_distances + epsilon)
        weights /= weights.sum()

        # Trim or extend returns to match requested horizon
        actual_horizon = min(horizon, nearest_returns.shape[1])
        trimmed_returns = nearest_returns[:, :actual_horizon]

        # Weighted forecast
        weighted_returns = np.average(trimmed_returns, axis=0, weights=weights)

        # Confidence bands via weighted quantiles
        lower_returns = np.array([
            _weighted_quantile(trimmed_returns[:, t], weights, 0.10)
            for t in range(actual_horizon)
        ])
        upper_returns = np.array([
            _weighted_quantile(trimmed_returns[:, t], weights, 0.90)
            for t in range(actual_horizon)
        ])

        base_price = float(close.iloc[-1])
        predicted = base_price * (1.0 + weighted_returns)
        lower = base_price * (1.0 + lower_returns)
        upper = base_price * (1.0 + upper_returns)

        # Generate future dates
        last_date = close.index[-1]
        if asset_type == "crypto":
            dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=actual_horizon, freq="D")
        else:
            dates = pd.bdate_range(last_date + pd.Timedelta(days=1), periods=actual_horizon)

        date_strings = [d.date().isoformat() for d in dates]

        return ForecastResult(
            dates=date_strings,
            predicted=predicted,
            lower=lower,
            upper=upper,
            neighbors_used=k,
        )

    def backtest(self, close: pd.Series, ohlcv: pd.DataFrame | None, n_folds: int = 5) -> BacktestMetrics:
        """Walk-forward cross-validation."""
        if ohlcv is not None and "Close" in ohlcv.columns:
            df = ohlcv
        else:
            df = pd.DataFrame({"Close": close})

        n = len(close)
        min_train = self.lookback + self.horizon + 50
        fold_size = max(self.horizon, (n - min_train) // n_folds)

        all_errors = []
        all_directions = []

        for fold in range(n_folds):
            test_end = n - fold * fold_size
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

            actual = close.iloc[test_start:test_end].to_numpy()
            actual_len = min(len(actual), len(result.predicted))
            pred = result.predicted[:actual_len]
            act = actual[:actual_len]

            errors = np.abs(pred - act)
            all_errors.extend(errors.tolist())

            # Directional accuracy
            if actual_len > 1:
                pred_direction = pred[-1] > pred[0]
                actual_direction = act[-1] > act[0]
                all_directions.append(1.0 if pred_direction == actual_direction else 0.0)

        if not all_errors:
            return BacktestMetrics(mae=0, rmse=0, mape=0, directional_accuracy=0.5, validation_windows=0)

        errors_arr = np.array(all_errors)
        mae = float(np.mean(errors_arr))
        rmse = float(np.sqrt(np.mean(errors_arr ** 2)))

        # MAPE (avoid division by zero)
        base = float(close.iloc[-1])
        mape = float(np.mean(errors_arr / max(base, 0.01))) * 100

        dir_acc = float(np.mean(all_directions)) if all_directions else 0.5

        return BacktestMetrics(
            mae=round(mae, 4),
            rmse=round(rmse, 4),
            mape=round(mape, 2),
            directional_accuracy=round(dir_acc, 4),
            validation_windows=len(all_directions),
        )


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    """Compute a weighted quantile."""
    sorted_idx = np.argsort(values)
    sorted_vals = values[sorted_idx]
    sorted_weights = weights[sorted_idx]
    cumulative = np.cumsum(sorted_weights)
    cutoff = quantile * cumulative[-1]
    idx = np.searchsorted(cumulative, cutoff)
    idx = min(idx, len(sorted_vals) - 1)
    return float(sorted_vals[idx])
