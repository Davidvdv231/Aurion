#!/usr/bin/env python3
"""Walk-forward evaluation of the ML analog model, the statistical baseline and a no-change forecast.

At every origin the models see only the previous `--history` rows (the app fetches about 500),
forecast `--horizon` days ahead and are scored against what actually happened.

Usage:
    python scripts/evaluate_forecasts.py --csv data/sp500.csv --csv data/msft.csv
    python scripts/evaluate_forecasts.py --ticker AAPL --ticker MSFT --period 10y

CSV files need a date column (first column or "Date") and Open/High/Low/Close/Volume columns.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.ml.model import AnalogForecastModel  # noqa: E402
from backend.services.forecast import build_stat_forecast  # noqa: E402

Z80 = 1.2816


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    date_col = "Date" if "Date" in df.columns else df.columns[0]
    df.index = pd.to_datetime(df[date_col])
    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float).sort_index()


def load_ticker(symbol: str, period: str) -> pd.DataFrame:
    import yfinance as yf

    df = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)


def ml_forecast(hist: pd.DataFrame, horizon: int):
    model = AnalogForecastModel(lookback=60, horizon=horizon, n_neighbors=24)
    model.fit(hist["Close"], hist)
    result = model.predict(hist["Close"], hist, horizon)
    return result.predicted, result.lower, result.upper


def stat_forecast(hist: pd.DataFrame, horizon: int):
    _, forecast, _ = build_stat_forecast(hist["Close"], horizon, "stock")
    return tuple(np.array([p[key] for p in forecast]) for key in ("predicted", "lower", "upper"))


def no_change_forecast(hist: pd.DataFrame, horizon: int):
    last = float(hist["Close"].iloc[-1])
    daily_vol = float(np.log(hist["Close"]).diff().tail(60).std())
    half = Z80 * daily_vol * np.sqrt(np.arange(1, horizon + 1))
    return np.full(horizon, last), last * np.exp(-half), last * np.exp(half)


MODELS = {"ML analog": ml_forecast, "Statistical": stat_forecast, "No change": no_change_forecast}


def evaluate(
    series: dict[str, pd.DataFrame], horizon: int, history: int, step: int
) -> pd.DataFrame:
    rows = []
    for name, df in series.items():
        close = df["Close"].to_numpy()
        for t in range(history, len(df) - horizon + 1, step):
            hist = df.iloc[t - history : t]
            actual, last = close[t : t + horizon], close[t - 1]
            for model_name, forecast in MODELS.items():
                try:
                    pred, lower, upper = forecast(hist, horizon)
                except (ValueError, RuntimeError):
                    continue
                ape = np.abs(pred - actual) / actual
                move = pred[-1] - last
                rows.append(
                    {
                        "model": model_name,
                        "series": name,
                        "path_mape": ape.mean() * 100,
                        "end_ape": ape[-1] * 100,
                        "direction": 0.5
                        if move == 0
                        else float(np.sign(move) == np.sign(actual[-1] - last)),
                        "coverage_80": float(np.mean((actual >= lower) & (actual <= upper))),
                        "range_width": float(np.mean((upper - lower) / last) * 100),
                    }
                )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--csv", type=Path, action="append", default=[])
    parser.add_argument("--ticker", action="append", default=[])
    parser.add_argument("--period", default="10y")
    parser.add_argument("--horizon", type=int, action="append")
    parser.add_argument("--history", type=int, default=500)
    parser.add_argument("--step", type=int, default=21)
    args = parser.parse_args()

    series = {path.stem: load_csv(path) for path in args.csv}
    series.update({symbol: load_ticker(symbol, args.period) for symbol in args.ticker})
    if not series:
        parser.error("pass at least one --csv or --ticker")

    for horizon in args.horizon or [30]:
        results = evaluate(series, horizon, args.history, args.step)
        summary = results.groupby("model")[
            ["path_mape", "end_ape", "direction", "coverage_80", "range_width"]
        ].mean()
        origins = len(results) // max(results["model"].nunique(), 1)
        print(f"\nHorizon {horizon} days, {origins} forecasts per model")
        print(summary.round(3).to_string())


if __name__ == "__main__":
    main()
