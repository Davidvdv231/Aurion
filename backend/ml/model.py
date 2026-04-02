from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backend.ml.dataset import SupervisedDataset, build_supervised_dataset
from backend.ml.features import FEATURE_COLUMNS, build_feature_frame


@dataclass(slots=True)
class ForecastPoint:
    date: str
    predicted: float
    lower: float
    upper: float


@dataclass(slots=True)
class ForecastOutput:
    model_name: str
    asset_type: str
    horizon: int
    last_close: float
    path: list[ForecastPoint]
    summary: dict[str, float | str]
    neighbors_used: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "asset_type": self.asset_type,
            "horizon": self.horizon,
            "last_close": self.last_close,
            "path": [
                {"date": point.date, "predicted": point.predicted, "lower": point.lower, "upper": point.upper}
                for point in self.path
            ],
            "summary": dict(self.summary),
            "neighbors_used": self.neighbors_used,
        }


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    order = np.argsort(values)
    ordered_values = values[order]
    ordered_weights = weights[order]
    cumulative = np.cumsum(ordered_weights)
    if cumulative.size == 0 or cumulative[-1] <= 0.0:
        return float(np.quantile(ordered_values, quantile))
    cutoff = quantile * cumulative[-1]
    index = int(np.searchsorted(cumulative, cutoff, side="left"))
    return float(ordered_values[min(index, len(ordered_values) - 1)])


def _soft_weights(distances: np.ndarray, *, gaussian: bool = False) -> np.ndarray:
    positive = distances[distances > 0.0]
    scale = float(np.median(positive)) if positive.size else 1.0
    scale = max(scale, 1e-6)
    if gaussian:
        weights = np.exp(-0.5 * np.square(distances / scale))
    else:
        weights = np.exp(-(distances / scale))
    if not np.any(weights):
        weights = np.ones_like(distances)
    return weights / weights.sum()


def _daily_from_cumulative(cumulative_returns: np.ndarray) -> np.ndarray:
    cumulative_returns = np.asarray(cumulative_returns, dtype=float)
    if cumulative_returns.ndim == 1:
        cumulative_returns = cumulative_returns.reshape(1, -1)

    daily = cumulative_returns.copy()
    if daily.shape[1] > 1:
        daily[:, 1:] = ((1.0 + cumulative_returns[:, 1:]) / (1.0 + cumulative_returns[:, :-1])) - 1.0
    return daily


def _cumulative_from_daily(daily_returns: np.ndarray) -> np.ndarray:
    daily_returns = np.asarray(daily_returns, dtype=float)
    if daily_returns.ndim == 1:
        daily_returns = daily_returns.reshape(1, -1)
    return np.cumprod(1.0 + daily_returns, axis=1) - 1.0


@dataclass(slots=True)
class AnalogForecastModel:
    lookback: int = 60
    horizon: int = 5
    top_k: int = 25
    feature_columns: tuple[str, ...] = field(default_factory=lambda: FEATURE_COLUMNS)
    model_name: str = "analog_forecaster"
    asset_type: str = "stock"
    feature_mean_: np.ndarray | None = None
    feature_std_: np.ndarray | None = None
    summary_mean_: np.ndarray | None = None
    summary_std_: np.ndarray | None = None
    train_vectors_: np.ndarray | None = None
    train_summary_vectors_: np.ndarray | None = None
    train_targets_: np.ndarray | None = None
    train_daily_targets_: np.ndarray | None = None
    train_anchor_dates_: list[str] = field(default_factory=list)
    train_anchor_closes_: np.ndarray | None = None
    blend_weights_: np.ndarray | None = None

    def fit(self, ohlcv: pd.DataFrame, asset_type: str | None = None) -> AnalogForecastModel:
        if asset_type is not None:
            self.asset_type = asset_type
        features = build_feature_frame(ohlcv)
        dataset = build_supervised_dataset(
            features,
            lookback=self.lookback,
            horizon=self.horizon,
            feature_columns=self.feature_columns,
        )
        self._fit_from_dataset(dataset)
        return self

    def _fit_from_dataset(self, dataset: SupervisedDataset) -> None:
        self.feature_columns = dataset.feature_columns
        feature_count = len(dataset.feature_columns)
        raw_windows = dataset.X.reshape(len(dataset.X), self.lookback, feature_count)
        summary_vectors = self._build_summary_vectors(raw_windows)

        self.feature_mean_ = dataset.X.mean(axis=0)
        self.feature_std_ = dataset.X.std(axis=0)
        self.feature_std_[self.feature_std_ == 0.0] = 1.0

        self.summary_mean_ = summary_vectors.mean(axis=0)
        self.summary_std_ = summary_vectors.std(axis=0)
        self.summary_std_[self.summary_std_ == 0.0] = 1.0

        self.train_vectors_ = self._standardize_sequences(dataset.X)
        self.train_summary_vectors_ = self._standardize_summaries(summary_vectors)
        self.train_targets_ = dataset.y.astype(float)
        self.train_daily_targets_ = _daily_from_cumulative(self.train_targets_)
        self.train_anchor_dates_ = [timestamp.date().isoformat() for timestamp in dataset.anchors]
        self.train_anchor_closes_ = dataset.anchor_closes.astype(float)
        self.blend_weights_ = self._calibrate_blend_weights()

    def _standardize_sequences(self, vectors: np.ndarray) -> np.ndarray:
        if self.feature_mean_ is None or self.feature_std_ is None:
            raise ValueError("Model is not fitted.")
        return (vectors - self.feature_mean_) / self.feature_std_

    def _standardize_summaries(self, vectors: np.ndarray) -> np.ndarray:
        if self.summary_mean_ is None or self.summary_std_ is None:
            raise ValueError("Model is not fitted.")
        return (vectors - self.summary_mean_) / self.summary_std_

    def _build_summary_vectors(self, windows: np.ndarray) -> np.ndarray:
        feature_index = {name: idx for idx, name in enumerate(self.feature_columns)}
        selected = [
            "return_1",
            "return_5",
            "volatility_5",
            "volatility_20",
            "macd",
            "macd_hist",
            "rsi_14",
            "price_to_sma_20",
            "volume_zscore_20",
            "high_low_range",
            "close_open_gap",
            "momentum_10",
        ]
        indices = [feature_index[name] for name in selected if name in feature_index]
        if not indices:
            return windows.reshape(len(windows), -1)

        short_span = min(5, self.lookback)
        medium_span = min(10, self.lookback)
        long_span = min(20, self.lookback)

        last_step = windows[:, -1, :][:, indices]
        short_mean = windows[:, -short_span:, :][:, :, indices].mean(axis=1)
        medium_mean = windows[:, -medium_span:, :][:, :, indices].mean(axis=1)
        long_mean = windows[:, -long_span:, :][:, :, indices].mean(axis=1)
        medium_std = windows[:, -medium_span:, :][:, :, indices].std(axis=1)
        return np.hstack([last_step, short_mean, medium_mean, long_mean, medium_std])

    def _latest_inputs(
        self,
        ohlcv: pd.DataFrame,
    ) -> tuple[np.ndarray, np.ndarray, float, pd.Timestamp, pd.DataFrame]:
        features = build_feature_frame(ohlcv)
        required = list(self.feature_columns) + ["close"]
        cleaned = features[required].dropna().copy()
        if len(cleaned) < self.lookback:
            raise ValueError("Not enough recent rows to make a forecast.")

        window = cleaned.iloc[-self.lookback :].copy()
        latest_vector = window[list(self.feature_columns)].to_numpy(dtype=float).reshape(1, -1)
        latest_window = window[list(self.feature_columns)].to_numpy(dtype=float).reshape(1, self.lookback, -1)
        return latest_vector, latest_window, float(window["close"].iloc[-1]), window.index[-1], window

    def _calibrate_blend_weights(self) -> np.ndarray:
        if self.train_vectors_ is None or self.train_summary_vectors_ is None or self.train_daily_targets_ is None:
            raise ValueError("Model is not fitted.")

        default = np.asarray([0.56, 0.44], dtype=float)
        sample_count = len(self.train_vectors_)
        if sample_count < 80:
            return default

        split = max(int(sample_count * 0.7), 40)
        if sample_count - split < 8:
            return default

        seq_errors: list[float] = []
        kernel_errors: list[float] = []
        max_validation = min(sample_count - split, 32)

        for idx in range(split, split + max_validation):
            train_seq = self.train_vectors_[:idx]
            train_summary = self.train_summary_vectors_[:idx]
            train_daily = self.train_daily_targets_[:idx]
            actual_cumulative = _cumulative_from_daily(self.train_daily_targets_[idx])[0]

            seq_distances = np.linalg.norm(train_seq - self.train_vectors_[idx], axis=1)
            seq_count = min(self.top_k, len(seq_distances))
            seq_indices = np.argsort(seq_distances)[:seq_count]
            seq_weights = _soft_weights(seq_distances[seq_indices], gaussian=False)
            seq_daily = np.average(train_daily[seq_indices], axis=0, weights=seq_weights)

            kernel_distances = np.linalg.norm(train_summary - self.train_summary_vectors_[idx], axis=1)
            kernel_count = min(max(self.top_k * 4, 40), len(kernel_distances))
            kernel_indices = np.argsort(kernel_distances)[:kernel_count]
            kernel_weights = _soft_weights(kernel_distances[kernel_indices], gaussian=True)
            kernel_daily = np.average(train_daily[kernel_indices], axis=0, weights=kernel_weights)

            seq_errors.append(float(np.mean(np.abs(_cumulative_from_daily(seq_daily)[0] - actual_cumulative))))
            kernel_errors.append(float(np.mean(np.abs(_cumulative_from_daily(kernel_daily)[0] - actual_cumulative))))

        if not seq_errors or not kernel_errors:
            return default

        seq_score = 1.0 / max(float(np.mean(seq_errors)), 1e-6)
        kernel_score = 1.0 / max(float(np.mean(kernel_errors)), 1e-6)
        learned = np.asarray([seq_score, kernel_score], dtype=float)
        learned = learned / learned.sum()
        blended = (0.65 * default) + (0.35 * learned)
        return blended / blended.sum()

    def _build_regime_bias(self, window: pd.DataFrame, last_close: float) -> tuple[np.ndarray, float]:
        latest = window.iloc[-1]
        recent_mean_return = float(window["return_1"].tail(min(5, len(window))).mean()) if "return_1" in window else 0.0
        rsi = float(latest.get("rsi_14", 50.0))
        macd_hist = float(latest.get("macd_hist", 0.0))
        price_to_sma = float(latest.get("price_to_sma_20", 0.0))
        volatility = float(latest.get("volatility_20", 0.0))
        momentum_raw = float(latest.get("momentum_10", 0.0))
        momentum = momentum_raw / max(last_close, 1e-6)

        trend_score = (
            0.34 * np.tanh(price_to_sma * 7.0)
            + 0.22 * np.tanh(macd_hist * 12.0)
            + 0.20 * np.tanh(momentum * 16.0)
            + 0.18 * np.tanh(recent_mean_return * 18.0)
            + 0.12 * np.tanh((rsi - 50.0) / 18.0)
        )

        if rsi > 72.0:
            trend_score -= 0.08 * np.tanh((rsi - 72.0) / 8.0)
        elif rsi < 28.0:
            trend_score += 0.08 * np.tanh((28.0 - rsi) / 8.0)

        volatility_drag = 1.0 - min(0.55, max(0.0, volatility / 0.08))
        base_bias = 0.0085 * trend_score * volatility_drag
        horizon_axis = np.arange(self.horizon, dtype=float)
        decay = np.exp(-horizon_axis / max(2.5, self.horizon / 3.0))
        curvature = 1.0 + 0.18 * np.sin(np.linspace(0.0, np.pi, self.horizon))
        bias = base_bias * decay * curvature
        strength = float(np.clip(abs(trend_score) * volatility_drag + abs(price_to_sma) * 2.0, 0.0, 1.0))
        return bias.astype(float), strength

    def predict(self, ohlcv: pd.DataFrame, asset_type: str | None = None, top_k: int | None = None) -> ForecastOutput:
        if (
            self.train_vectors_ is None
            or self.train_summary_vectors_ is None
            or self.train_targets_ is None
            or self.train_daily_targets_ is None
        ):
            raise ValueError("Model must be fitted before prediction.")

        effective_asset_type = asset_type or self.asset_type
        latest_vector, latest_window, last_close, last_date, latest_frame = self._latest_inputs(ohlcv)
        sequence_query = self._standardize_sequences(latest_vector)[0]
        summary_query = self._standardize_summaries(self._build_summary_vectors(latest_window))[0]

        top_neighbor_count = min(int(top_k or self.top_k), len(self.train_vectors_))
        sequence_distances = np.linalg.norm(self.train_vectors_ - sequence_query, axis=1)
        sequence_indices = np.argsort(sequence_distances)[:top_neighbor_count]
        sequence_weights = _soft_weights(sequence_distances[sequence_indices], gaussian=False)

        kernel_neighbor_count = min(max(top_neighbor_count * 4, 40), len(self.train_summary_vectors_))
        kernel_distances = np.linalg.norm(self.train_summary_vectors_ - summary_query, axis=1)
        kernel_indices = np.argsort(kernel_distances)[:kernel_neighbor_count]
        kernel_weights = _soft_weights(kernel_distances[kernel_indices], gaussian=True)

        sequence_daily = np.average(self.train_daily_targets_[sequence_indices], axis=0, weights=sequence_weights)
        kernel_daily = np.average(self.train_daily_targets_[kernel_indices], axis=0, weights=kernel_weights)

        regime_bias, regime_strength = self._build_regime_bias(latest_frame, last_close)
        disagreement = float(np.mean(np.abs(sequence_daily - kernel_daily)))
        base_weights = self.blend_weights_.copy() if self.blend_weights_ is not None else np.asarray([0.56, 0.44], dtype=float)
        kernel_boost = min(0.18, regime_strength * 0.14)
        base_weights[0] = max(0.20, base_weights[0] - kernel_boost)
        base_weights[1] = min(0.80, base_weights[1] + kernel_boost)
        base_weights = base_weights / base_weights.sum()

        regime_weight = float(np.clip(0.09 + (regime_strength * 0.12) + (disagreement * 2.5), 0.08, 0.24))
        remainder = max(0.76, 1.0 - regime_weight)
        sequence_weight = remainder * float(base_weights[0])
        kernel_weight = remainder * float(base_weights[1])
        total_weight = sequence_weight + kernel_weight + regime_weight
        sequence_weight /= total_weight
        kernel_weight /= total_weight
        regime_weight /= total_weight

        return_cap = 0.18 if effective_asset_type == "crypto" else 0.10
        predicted_daily = (
            (sequence_weight * sequence_daily)
            + (kernel_weight * kernel_daily)
            + (regime_weight * regime_bias)
        )
        predicted_daily = np.clip(predicted_daily, -return_cap, return_cap)
        predicted_cumulative = _cumulative_from_daily(predicted_daily)[0]

        candidate_sequence = self.train_daily_targets_[sequence_indices[: min(len(sequence_indices), max(8, top_neighbor_count))]]
        candidate_kernel = self.train_daily_targets_[kernel_indices[: min(len(kernel_indices), max(16, top_neighbor_count * 2))]]
        candidate_paths = np.vstack([candidate_sequence, candidate_kernel])
        candidate_weights = np.concatenate(
            [
                sequence_weights[: len(candidate_sequence)] * sequence_weight,
                kernel_weights[: len(candidate_kernel)] * kernel_weight,
            ]
        )
        candidate_weights = candidate_weights / candidate_weights.sum()
        adjusted_candidates = np.clip(candidate_paths + (regime_weight * regime_bias), -return_cap, return_cap)
        candidate_cumulative = _cumulative_from_daily(adjusted_candidates)

        lower_returns = np.asarray(
            [_weighted_quantile(candidate_cumulative[:, step], candidate_weights, 0.12) for step in range(self.horizon)],
            dtype=float,
        )
        upper_returns = np.asarray(
            [_weighted_quantile(candidate_cumulative[:, step], candidate_weights, 0.88) for step in range(self.horizon)],
            dtype=float,
        )

        path_prices = np.maximum(0.01, last_close * (1.0 + predicted_cumulative))
        lower_prices = np.maximum(0.01, last_close * (1.0 + lower_returns))
        upper_prices = np.maximum(lower_prices + 0.01, last_close * (1.0 + upper_returns))

        if effective_asset_type == "crypto":
            future_dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=self.horizon, freq="D")
        else:
            future_dates = pd.bdate_range(last_date + pd.Timedelta(days=1), periods=self.horizon)

        path = [
            ForecastPoint(
                date=timestamp.date().isoformat(),
                predicted=float(round(predicted, 4)),
                lower=float(round(lower, 4)),
                upper=float(round(upper, 4)),
            )
            for timestamp, predicted, lower, upper in zip(future_dates, path_prices, lower_prices, upper_prices)
        ]

        expected_return_pct = float(predicted_cumulative[-1] * 100.0)
        daily_trend_pct = float(predicted_daily[0] * 100.0)
        path_dispersion = float(np.average(np.std(candidate_cumulative, axis=1), weights=candidate_weights))
        confidence = float(np.clip(1.0 - min(1.0, (path_dispersion * 8.0) + (disagreement * 4.0)), 0.08, 0.95))
        probability_up = float(np.clip(np.sum(candidate_weights * (candidate_cumulative[:, -1] > 0.0)), 0.0, 1.0))

        if expected_return_pct > 0.8:
            trend = "bullish"
        elif expected_return_pct < -0.8:
            trend = "bearish"
        else:
            trend = "neutral"

        if probability_up >= 0.60 and confidence >= 0.46 and expected_return_pct >= 1.25:
            signal = "buy"
        elif probability_up <= 0.40 and confidence >= 0.46 and expected_return_pct <= -1.25:
            signal = "sell"
        else:
            signal = "hold"

        summary = {
            "last_close": float(round(last_close, 4)),
            "expected_return_pct": float(round(expected_return_pct, 4)),
            "daily_trend_pct": float(round(daily_trend_pct, 4)),
            "confidence": float(round(confidence, 4)),
            "probability_up": float(round(probability_up, 4)),
            "trend": trend,
            "signal": signal,
            "sequence_weight": float(round(sequence_weight, 4)),
            "kernel_weight": float(round(kernel_weight, 4)),
            "regime_weight": float(round(regime_weight, 4)),
            "median_sequence_distance": float(round(float(np.median(sequence_distances[sequence_indices])), 6)),
            "median_regime_distance": float(round(float(np.median(kernel_distances[kernel_indices])), 6)),
        }
        return ForecastOutput(
            model_name=self.model_name,
            asset_type=effective_asset_type,
            horizon=self.horizon,
            last_close=float(round(last_close, 4)),
            path=path,
            summary=summary,
            neighbors_used=int(top_neighbor_count + min(len(kernel_indices), max(16, top_neighbor_count * 2))),
        )

    def to_state(self) -> dict[str, Any]:
        if (
            self.feature_mean_ is None
            or self.feature_std_ is None
            or self.summary_mean_ is None
            or self.summary_std_ is None
            or self.train_vectors_ is None
            or self.train_summary_vectors_ is None
            or self.train_targets_ is None
            or self.train_daily_targets_ is None
            or self.train_anchor_closes_ is None
            or self.blend_weights_ is None
        ):
            raise ValueError("Model is not fitted.")

        return {
            "lookback": self.lookback,
            "horizon": self.horizon,
            "top_k": self.top_k,
            "feature_columns": list(self.feature_columns),
            "model_name": self.model_name,
            "asset_type": self.asset_type,
            "feature_mean": self.feature_mean_,
            "feature_std": self.feature_std_,
            "summary_mean": self.summary_mean_,
            "summary_std": self.summary_std_,
            "train_vectors": self.train_vectors_,
            "train_summary_vectors": self.train_summary_vectors_,
            "train_targets": self.train_targets_,
            "train_daily_targets": self.train_daily_targets_,
            "train_anchor_dates": np.asarray(self.train_anchor_dates_, dtype=object),
            "train_anchor_closes": self.train_anchor_closes_,
            "blend_weights": self.blend_weights_,
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> AnalogForecastModel:
        model = cls(
            lookback=int(state["lookback"]),
            horizon=int(state["horizon"]),
            top_k=int(state["top_k"]),
            feature_columns=tuple(state["feature_columns"]),
            model_name=str(state["model_name"]),
            asset_type=str(state["asset_type"]),
        )
        model.feature_mean_ = np.asarray(state["feature_mean"], dtype=float)
        model.feature_std_ = np.asarray(state["feature_std"], dtype=float)
        model.summary_mean_ = np.asarray(state["summary_mean"], dtype=float)
        model.summary_std_ = np.asarray(state["summary_std"], dtype=float)
        model.train_vectors_ = np.asarray(state["train_vectors"], dtype=float)
        model.train_summary_vectors_ = np.asarray(state["train_summary_vectors"], dtype=float)
        model.train_targets_ = np.asarray(state["train_targets"], dtype=float)
        model.train_daily_targets_ = np.asarray(state["train_daily_targets"], dtype=float)
        model.train_anchor_dates_ = [str(item) for item in np.asarray(state["train_anchor_dates"], dtype=object).tolist()]
        model.train_anchor_closes_ = np.asarray(state["train_anchor_closes"], dtype=float)
        model.blend_weights_ = np.asarray(state["blend_weights"], dtype=float)
        return model
