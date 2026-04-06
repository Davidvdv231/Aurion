#!/usr/bin/env python3
"""Generate backtest comparison between ML analog forecaster and statistical baseline.

Usage:
    python scripts/generate_backtest.py

Outputs a comparison table to stdout and writes results to docs/backtest_results.md.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure the project root is on sys.path so backend imports work.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import yfinance as yf

from backend.ml.model import AnalogForecastModel, BacktestMetrics
from backend.ml.service import train_and_predict
from backend.services.forecast import backtest_stat_forecast

TICKERS: list[tuple[str, str]] = [
    ("AAPL", "stock"),
    ("MSFT", "stock"),
    ("GOOG", "stock"),
    ("TSLA", "stock"),
    ("AMZN", "stock"),
    ("NVDA", "stock"),
    ("BTC-USD", "crypto"),
    ("ETH-USD", "crypto"),
]

HORIZON = 30
BACKTEST_FOLDS = 5
MIN_ROWS = 180


def fetch_history(symbol: str, asset_type: str) -> pd.Series | None:
    """Download historical close prices via yfinance."""
    try:
        period = "2y" if asset_type == "stock" else "2y"
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, auto_adjust=True)
        if hist.empty or len(hist) < MIN_ROWS:
            print(f"  [SKIP] {symbol}: insufficient data ({len(hist)} rows)")
            return None
        close = hist["Close"].dropna()
        close.index = pd.DatetimeIndex(close.index).tz_localize(None)
        return close
    except Exception as exc:
        print(f"  [ERROR] {symbol}: {exc}")
        return None


def run_backtest(
    symbol: str,
    close: pd.Series,
    asset_type: str,
) -> dict:
    """Run both ML and stat backtests; return a result dict."""
    result: dict = {
        "symbol": symbol,
        "asset_type": asset_type,
        "rows": len(close),
        "ml_mae": None,
        "ml_mape": None,
        "ml_dir_acc": None,
        "ml_windows": None,
        "stat_mape": None,
        "stat_dir_acc": None,
        "stat_windows": None,
        "ml_beats_stat": None,
        "ml_error": None,
    }

    # Statistical backtest
    try:
        stat_metrics = backtest_stat_forecast(close, HORIZON, asset_type, n_folds=BACKTEST_FOLDS)
        result["stat_mape"] = stat_metrics["mape"]
        result["stat_dir_acc"] = stat_metrics["directional_accuracy"]
        result["stat_windows"] = stat_metrics["validation_windows"]
    except Exception as exc:
        result["stat_mape"] = None
        result["stat_dir_acc"] = None
        print(f"  [WARN] {symbol} stat backtest failed: {exc}")

    # ML backtest
    try:
        _, ml_metrics = train_and_predict(
            symbol=symbol,
            close=close,
            horizon=HORIZON,
            asset_type=asset_type,
            n_neighbors=24,
            lookback=60,
            backtest_folds=BACKTEST_FOLDS,
        )
        result["ml_mae"] = ml_metrics.mae
        result["ml_mape"] = ml_metrics.mape
        result["ml_dir_acc"] = ml_metrics.directional_accuracy
        result["ml_windows"] = ml_metrics.validation_windows
    except Exception as exc:
        result["ml_error"] = str(exc)
        print(f"  [WARN] {symbol} ML backtest failed: {exc}")

    # Compare
    if result["ml_mape"] is not None and result["stat_mape"] is not None:
        result["ml_beats_stat"] = result["ml_mape"] < result["stat_mape"]

    return result


def format_value(value, fmt: str = ".2f") -> str:
    """Format a numeric value or return 'N/A'."""
    if value is None:
        return "N/A"
    return f"{value:{fmt}}"


def build_table(results: list[dict]) -> str:
    """Build a Markdown table from backtest results."""
    header = (
        "| Ticker | Type | Rows | ML MAE | ML MAPE% | ML Dir.Acc | "
        "Stat MAPE% | Stat Dir.Acc | ML Beats Stat | Notes |\n"
        "|--------|------|------|--------|----------|------------|"
        "------------|--------------|---------------|-------|\n"
    )
    rows: list[str] = []
    for r in results:
        beat = ""
        if r["ml_beats_stat"] is True:
            beat = "YES"
        elif r["ml_beats_stat"] is False:
            beat = "no"
        else:
            beat = "N/A"

        notes = r.get("ml_error") or ""
        if notes and len(notes) > 30:
            notes = notes[:30] + "..."

        row = (
            f"| {r['symbol']} "
            f"| {r['asset_type']} "
            f"| {r['rows']} "
            f"| {format_value(r['ml_mae'])} "
            f"| {format_value(r['ml_mape'])} "
            f"| {format_value(r['ml_dir_acc'], '.4f')} "
            f"| {format_value(r['stat_mape'])} "
            f"| {format_value(r['stat_dir_acc'], '.4f')} "
            f"| {beat} "
            f"| {notes} |"
        )
        rows.append(row)

    return header + "\n".join(rows)


def build_summary(results: list[dict]) -> str:
    """Build a summary section."""
    total = len(results)
    ml_ok = sum(1 for r in results if r["ml_mape"] is not None)
    ml_wins = sum(1 for r in results if r["ml_beats_stat"] is True)
    stat_wins = sum(1 for r in results if r["ml_beats_stat"] is False)
    ties = ml_ok - ml_wins - stat_wins

    ml_mapes = [r["ml_mape"] for r in results if r["ml_mape"] is not None]
    stat_mapes = [r["stat_mape"] for r in results if r["stat_mape"] is not None]
    ml_dir_accs = [r["ml_dir_acc"] for r in results if r["ml_dir_acc"] is not None]

    lines = [
        f"- **Tickers evaluated**: {total}",
        f"- **ML models trained**: {ml_ok}",
        f"- **ML wins (lower MAPE)**: {ml_wins}",
        f"- **Stat wins**: {stat_wins}",
    ]
    if ml_mapes:
        lines.append(f"- **Avg ML MAPE**: {np.mean(ml_mapes):.2f}%")
    if stat_mapes:
        lines.append(f"- **Avg Stat MAPE**: {np.mean(stat_mapes):.2f}%")
    if ml_dir_accs:
        lines.append(f"- **Avg ML Directional Accuracy**: {np.mean(ml_dir_accs):.4f}")

    return "\n".join(lines)


def main() -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"=== Aurion Backtest Report ({timestamp}) ===\n")
    print(f"Horizon: {HORIZON} days | Folds: {BACKTEST_FOLDS}\n")

    results: list[dict] = []

    for symbol, asset_type in TICKERS:
        print(f"Processing {symbol} ({asset_type})...")
        t0 = time.perf_counter()

        close = fetch_history(symbol, asset_type)
        if close is None:
            continue

        result = run_backtest(symbol, close, asset_type)
        elapsed = time.perf_counter() - t0
        print(f"  Done in {elapsed:.1f}s")
        results.append(result)

    if not results:
        print("\nNo tickers could be processed.")
        sys.exit(1)

    # Print to stdout
    table = build_table(results)
    summary = build_summary(results)

    print("\n" + table)
    print("\n### Summary\n")
    print(summary)

    # Write to docs/backtest_results.md
    docs_dir = ROOT / "docs"
    docs_dir.mkdir(exist_ok=True)
    output_path = docs_dir / "backtest_results.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Aurion Backtest Results\n\n")
        f.write(f"Generated: {timestamp}\n\n")
        f.write(f"**Configuration**: horizon={HORIZON} days, folds={BACKTEST_FOLDS}\n\n")
        f.write("## Results\n\n")
        f.write(table)
        f.write("\n\n## Summary\n\n")
        f.write(summary)
        f.write("\n\n## Notes\n\n")
        f.write("- **ML MAE**: Mean Absolute Error of the ML analog forecaster\n")
        f.write("- **MAPE**: Mean Absolute Percentage Error (lower is better)\n")
        f.write("- **Dir.Acc**: Directional accuracy -- fraction of days where predicted direction matched actual\n")
        f.write("- **ML Beats Stat**: Whether the ML model achieved lower MAPE than the statistical baseline\n")
        f.write("- Statistical baseline uses log-linear trend extrapolation with cross-validation\n")
        f.write("- ML model uses k-nearest-neighbor analog pattern matching\n")

    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    main()
