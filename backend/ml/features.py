"""Technical indicator feature engineering for the ML pipeline."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger("stock_predictor.features")

# Largest rolling window across all features (sma_50 → rolling(50)).
# Rows before this position lack fully-warmed indicators and must be
# discarded before training.  Update this when adding longer windows.
_FEATURE_WARMUP_ROWS = 50


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute 23 technical indicator features from OHLCV data.

    Expects a DataFrame with at least a 'Close' column (and optionally
    'High', 'Low', 'Volume').  Returns a new DataFrame with the same
    index containing only the feature columns.
    """
    close = df["Close"].astype(float)
    high = df["High"].astype(float) if "High" in df else close
    low = df["Low"].astype(float) if "Low" in df else close
    volume = df["Volume"].astype(float) if "Volume" in df else pd.Series(0.0, index=close.index)

    features = pd.DataFrame(index=close.index)

    # --- Returns ---
    features["return_1"] = close.pct_change(1)
    features["log_return_1"] = np.log(close / close.shift(1))
    features["return_5"] = close.pct_change(5)

    # --- Volatility ---
    features["volatility_5"] = features["return_1"].rolling(5).std()
    features["volatility_20"] = features["return_1"].rolling(20).std()

    # --- Simple Moving Averages ---
    for window in (5, 10, 20, 50):
        features[f"sma_{window}"] = close.rolling(window).mean() / close - 1.0

    # --- Exponential Moving Averages ---
    features["ema_12"] = close.ewm(span=12, adjust=False).mean() / close - 1.0
    features["ema_26"] = close.ewm(span=26, adjust=False).mean() / close - 1.0

    # --- MACD ---
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    features["macd"] = macd_line / close
    features["macd_signal"] = signal_line / close
    features["macd_hist"] = (macd_line - signal_line) / close

    # --- RSI ---
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    features["rsi_14"] = 100 - (100 / (1 + rs))

    # --- Momentum ---
    features["momentum_10"] = close / close.shift(10) - 1.0

    # --- Bollinger Bands ---
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    features["bb_bandwidth"] = (2 * bb_std) / bb_mid.replace(0, np.nan)
    features["bb_position"] = (close - bb_mid) / (bb_std.replace(0, np.nan))

    # --- Price ratios ---
    features["price_to_sma_20"] = close / bb_mid - 1.0
    features["high_low_range"] = (high - low) / close
    features["close_open_gap"] = (close - df.get("Open", close)) / close

    # --- Volume ---
    # When no real volume data exists (Close-only input), all values are 0.
    # Avoid 0/NaN explosions by filling with neutral 0.0 instead.
    has_real_volume = "Volume" in df and (volume != 0).any()
    if has_real_volume:
        vol_ma5 = volume.rolling(5).mean().replace(0, np.nan)
        features["volume_change_5"] = volume / vol_ma5 - 1.0
        vol_ma20 = volume.rolling(20).mean()
        vol_std20 = volume.rolling(20).std().replace(0, np.nan)
        features["volume_zscore_20"] = (volume - vol_ma20) / vol_std20
    else:
        features["volume_change_5"] = 0.0
        features["volume_zscore_20"] = 0.0

    # --- Warm-up removal ---
    # Explicitly discard the first _FEATURE_WARMUP_ROWS rows where rolling
    # indicators are not yet fully defined.  This replaces the old implicit
    # ffill-then-dropna strategy that silently depended on sma_50 being the
    # widest window.
    features = features.iloc[_FEATURE_WARMUP_ROWS:]

    # Safety net: drop any remaining NaN rows that slipped through
    # (e.g. from division-by-zero in edge-case data).
    pre_count = len(features)
    remaining_nan = features.isna().any(axis=1).sum()
    if remaining_nan > 0:
        nan_cols = features.columns[features.isna().any()].tolist()
        logger.warning(
            "Feature NaN guard: %d rows still have NaN after warm-up removal (%s), dropping",
            int(remaining_nan),
            ", ".join(nan_cols[:5]),
        )
        features = features.dropna()

    return features


FEATURE_COLUMNS = [
    "return_1", "log_return_1", "return_5",
    "volatility_5", "volatility_20",
    "sma_5", "sma_10", "sma_20", "sma_50",
    "ema_12", "ema_26",
    "macd", "macd_signal", "macd_hist",
    "rsi_14", "momentum_10",
    "bb_bandwidth", "bb_position",
    "price_to_sma_20", "high_low_range", "close_open_gap",
    "volume_change_5", "volume_zscore_20",
]
