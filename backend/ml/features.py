from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


FEATURE_COLUMNS = (
    "return_1",
    "log_return_1",
    "return_5",
    "volatility_5",
    "volatility_20",
    "sma_5",
    "sma_10",
    "sma_20",
    "sma_50",
    "ema_12",
    "ema_26",
    "macd",
    "macd_signal",
    "macd_hist",
    "rsi_14",
    "bollinger_mid_20",
    "bollinger_upper_20",
    "bollinger_lower_20",
    "bollinger_bandwidth_20",
    "price_to_sma_20",
    "volume_change_5",
    "volume_zscore_20",
    "high_low_range",
    "close_open_gap",
    "momentum_10",
)


@dataclass(slots=True)
class FeatureFrameConfig:
    close_column: str = "close"
    open_column: str = "open"
    high_column: str = "high"
    low_column: str = "low"
    volume_column: str = "volume"


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace(0.0, np.nan)
    return (numerator / denominator).replace([np.inf, -np.inf], np.nan)


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def build_feature_frame(ohlcv: pd.DataFrame, config: FeatureFrameConfig | None = None) -> pd.DataFrame:
    config = config or FeatureFrameConfig()
    frame = ohlcv.copy()
    frame.columns = [str(column).lower() for column in frame.columns]
    frame = frame.sort_index()

    if config.close_column not in frame.columns:
        raise ValueError("Missing required close column.")

    close = frame[config.close_column].astype(float)
    open_ = frame[config.open_column].astype(float) if config.open_column in frame.columns else close.shift(1)
    high = frame[config.high_column].astype(float) if config.high_column in frame.columns else close
    low = frame[config.low_column].astype(float) if config.low_column in frame.columns else close
    volume = frame[config.volume_column].astype(float) if config.volume_column in frame.columns else pd.Series(index=frame.index, data=np.nan)

    features = pd.DataFrame(index=frame.index)
    features["close"] = close
    features["open"] = open_
    features["high"] = high
    features["low"] = low
    features["volume"] = volume
    features["return_1"] = close.pct_change()
    features["log_return_1"] = np.log(close / close.shift(1))
    features["return_5"] = close.pct_change(periods=5)
    features["volatility_5"] = features["return_1"].rolling(5).std(ddof=0)
    features["volatility_20"] = features["return_1"].rolling(20).std(ddof=0)
    features["sma_5"] = close.rolling(5).mean()
    features["sma_10"] = close.rolling(10).mean()
    features["sma_20"] = close.rolling(20).mean()
    features["sma_50"] = close.rolling(50).mean()
    features["ema_12"] = _ema(close, 12)
    features["ema_26"] = _ema(close, 26)
    features["macd"] = features["ema_12"] - features["ema_26"]
    features["macd_signal"] = _ema(features["macd"], 9)
    features["macd_hist"] = features["macd"] - features["macd_signal"]
    features["rsi_14"] = _rsi(close, 14)

    bollinger_mid = close.rolling(20).mean()
    bollinger_std = close.rolling(20).std(ddof=0)
    features["bollinger_mid_20"] = bollinger_mid
    features["bollinger_upper_20"] = bollinger_mid + (2.0 * bollinger_std)
    features["bollinger_lower_20"] = bollinger_mid - (2.0 * bollinger_std)
    features["bollinger_bandwidth_20"] = _safe_divide(
        features["bollinger_upper_20"] - features["bollinger_lower_20"],
        features["bollinger_mid_20"],
    )
    features["price_to_sma_20"] = _safe_divide(close, features["sma_20"]) - 1.0
    features["volume_change_5"] = volume.pct_change(periods=5)
    features["volume_zscore_20"] = _safe_divide(volume - volume.rolling(20).mean(), volume.rolling(20).std(ddof=0))
    features["high_low_range"] = _safe_divide(high - low, close)
    features["close_open_gap"] = _safe_divide(close - open_, open_)
    features["momentum_10"] = close.diff(10)

    features.replace([np.inf, -np.inf], np.nan, inplace=True)
    return features
