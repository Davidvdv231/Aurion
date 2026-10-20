"""Analog Pattern Forecaster - non-linear nearest-neighbor ensemble model."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.ml.features import FEATURE_COLUMNS, compute_features

_Z80 = 1.2816
_VOLATILITY_FEATURE = FEATURE_COLUMNS.index("volatility_20")


def directional_hit_rate(predicted: np.ndarray, actual: np.ndarray, origin: float) -> float:
    """Share of forecast days on the correct side of the origin price; a flat call counts as half."""
    predicted_side = np.sign(np.asarray(predicted, dtype=np.float64) - origin)
    actual_side = np.sign(np.asarray(actual, dtype=np.float64) - origin)
    hits = np.where(predicted_side == 0, 0.5, (predicted_side == actual_side).astype(np.float64))
    return float(np.mean(hits))


def _shrink_toward_no_change(
    log_returns: np.ndarray, weights: np.ndarray, mean: np.ndarray
) -> np.ndarray:
    """Positive-part James-Stein: keep the analog mean only where it stands out from its own noise."""
    effective_n = 1.0 / np.sum(weights**2)
    variance = np.average((log_returns - mean) ** 2, axis=0, weights=weights)
    factor = np.clip(1.0 - (variance / effective_n) / np.maximum(mean**2, 1e-12), 0.0, 1.0)
    return factor * mean


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
    analog_mean_return_pct: float = 0.0
    shrunk_toward_no_change: bool = False


@dataclass(slots=True)
class BacktestMetrics:
    mae: float
    rmse: float
    mape: float
    directional_accuracy: float
    validation_windows: int
    coverage_80: float | None = None
    mean_error: float | None = None
    # MAPE of holding the last close flat over the same windows: the bar a forecast has to clear.
    no_change_mape: float | None = None


@dataclass
class AnalogForecastModel:
    """K-nearest-neighbor analog forecaster on normalized technical features."""

    lookback: int = 60
    horizon: int = 30
    n_neighbors: int = 24
    # Keeps analogs distinct episodes (adjacent windows overlap); 15 tested best for 7-45 days.
    min_separation: int = 15
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
            "min_separation": self.min_separation,
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
            min_separation=int(state.get("min_separation", 15)),
        )
        model._feature_mean = np.asarray(state["feature_mean"])
        model._feature_std = np.asarray(state["feature_std"])
        model._feature_raw_std = np.asarray(state.get("feature_raw_std", np.array([])))
        model._windows = np.asarray(state["windows"])
        model._future_returns = np.asarray(state["future_returns"])
        model._window_end_features_raw = np.asarray(
            state.get("window_end_features_raw", np.array([]))
        )
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
            window = normalized[i - self.lookback : i]
            if np.any(np.isnan(window)):
                continue

            base_price = close_arr[i - 1]
            if base_price <= 0:
                continue

            future_prices = close_arr[i : i + self.horizon]
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

        if ohlcv is not None and "Close" in ohlcv.columns:
            df = ohlcv
        else:
            df = pd.DataFrame({"Close": close})

        features = compute_features(df)
        feat_matrix = features[FEATURE_COLUMNS].to_numpy(dtype=np.float64)
        # Safety net: same nan_to_num as fit() to guarantee identical transform.
        feat_matrix = np.nan_to_num(feat_matrix, nan=0.0, posinf=0.0, neginf=0.0)

        normalized = (feat_matrix - self._feature_mean) / self._feature_std
        query = normalized[-self.lookback :].flatten()

        diffs = self._windows - query
        distances = np.sqrt(np.sum(diffs**2, axis=1))
        nearest_idx = self._select_neighbors(distances)
        k = len(nearest_idx)
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

        log_returns = np.log1p(nearest_returns)
        mean_log = np.average(log_returns, axis=0, weights=weights)
        center = _shrink_toward_no_change(log_returns, weights, mean_log)
        analog_low = (
            np.array([_weighted_quantile(log_returns[:, t], weights, 0.10) for t in range(horizon)])
            - mean_log
        )
        analog_high = (
            np.array([_weighted_quantile(log_returns[:, t], weights, 0.90) for t in range(horizon)])
            - mean_log
        )
        steps = np.arange(1, horizon + 1, dtype=np.float64)
        current_volatility = max(float(feat_matrix[-1, _VOLATILITY_FEATURE]), 0.0)
        volatility_half_width = _Z80 * current_volatility * np.sqrt(steps)
        # The analogs' own spread under-covers on its own, so average it with a volatility band.
        lower_log = np.minimum(center + 0.5 * (analog_low - volatility_half_width), center)
        upper_log = np.maximum(center + 0.5 * (analog_high + volatility_half_width), center)

        base_price = float(close.iloc[-1])
        predicted = base_price * np.exp(center)
        lower = base_price * np.exp(lower_log)
        upper = base_price * np.exp(upper_log)

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
            analog_mean_return_pct=round(float(np.expm1(mean_log[-1])) * 100, 2),
            shrunk_toward_no_change=bool(abs(center[-1]) < 0.5 * abs(mean_log[-1])),
        )

    def _select_neighbors(self, distances: np.ndarray) -> np.ndarray:
        """Nearest windows whose end rows are at least `min_separation` apart."""
        order = np.argsort(distances, kind="stable")
        positions = self._window_end_positions
        if len(positions) != len(distances):
            return order[: self.n_neighbors]

        separation = max(1, self.min_separation)
        chosen: list[int] = []
        for idx in order:
            position = int(positions[idx])
            if all(abs(position - int(positions[c])) >= separation for c in chosen):
                chosen.append(int(idx))
                if len(chosen) == self.n_neighbors:
                    break
        return np.array(chosen, dtype=np.int64)

    def backtest(
        self, close: pd.Series, ohlcv: pd.DataFrame | None, n_folds: int = 5
    ) -> BacktestMetrics:
        if ohlcv is not None and "Close" in ohlcv.columns:
            df = ohlcv
        else:
            df = pd.DataFrame({"Close": close})

        n = len(close)
        min_train = self.lookback + self.horizon + 50
        fold_size = max(self.horizon, (n - min_train) // max(n_folds, 1))

        all_errors = []
        all_no_change_errors: list[float] = []
        all_actuals = []
        all_directions = []
        all_signed_errors: list[float] = []
        all_within_band: list[bool] = []

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
                min_separation=self.min_separation,
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
            lower = result.lower[:actual_len]
            upper = result.upper[:actual_len]
            errors = np.abs(pred - act)
            all_errors.extend(errors.tolist())
            all_no_change_errors.extend(np.abs(float(train_close.iloc[-1]) - act).tolist())
            all_actuals.extend(act.tolist())
            all_signed_errors.extend((pred - act).tolist())

            for i in range(actual_len):
                all_within_band.append(bool(lower[i] <= act[i] <= upper[i]))

            all_directions.append(directional_hit_rate(pred, act, float(train_close.iloc[-1])))

        if not all_errors:
            return BacktestMetrics(
                mae=0,
                rmse=0,
                mape=0,
                directional_accuracy=0.5,
                validation_windows=0,
                coverage_80=None,
                mean_error=None,
            )

        errors_arr = np.array(all_errors)
        actuals_arr = np.array(all_actuals)
        mae = float(np.mean(errors_arr))
        rmse = float(np.sqrt(np.mean(errors_arr**2)))

        # MAPE: pointwise |error| / |actual|, skipping zero actuals
        nonzero = np.abs(actuals_arr) > 0
        mape = (
            float(np.mean(errors_arr[nonzero] / np.abs(actuals_arr[nonzero]))) * 100
            if np.any(nonzero)
            else 0.0
        )
        no_change_arr = np.array(all_no_change_errors)
        no_change_mape = (
            float(np.mean(no_change_arr[nonzero] / np.abs(actuals_arr[nonzero]))) * 100
            if np.any(nonzero)
            else 0.0
        )

        dir_acc = float(np.mean(all_directions)) if all_directions else 0.5

        coverage_80 = (
            round(sum(all_within_band) / len(all_within_band), 4) if all_within_band else None
        )
        mean_error = round(float(np.mean(all_signed_errors)), 4) if all_signed_errors else None

        return BacktestMetrics(
            mae=round(mae, 4),
            rmse=round(rmse, 4),
            mape=round(mape, 2),
            directional_accuracy=round(dir_acc, 4),
            validation_windows=len(all_directions),
            coverage_80=coverage_80,
            mean_error=mean_error,
            no_change_mape=round(no_change_mape, 2),
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
