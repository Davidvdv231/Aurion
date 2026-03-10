from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Stock Predictor API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _fetch_close_prices(symbol: str) -> pd.Series:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=730)

    frame = yf.download(
        symbol,
        start=start.date(),
        end=(end + timedelta(days=1)).date(),
        interval="1d",
        auto_adjust=True,
        progress=False,
    )

    if frame.empty or "Close" not in frame:
        raise HTTPException(status_code=404, detail="Geen koersdata gevonden voor dit ticker symbool.")

    close_column = frame["Close"]
    close = close_column.iloc[:, 0] if isinstance(close_column, pd.DataFrame) else close_column
    close = close.dropna()

    if len(close) < 60:
        raise HTTPException(
            status_code=400,
            detail="Onvoldoende data om een betrouwbare 1-maands voorspelling te maken.",
        )

    return close


def _build_forecast(close: pd.Series, horizon: int) -> tuple[list[dict], list[dict], dict]:
    values = close.astype(float).to_numpy()
    log_values = np.log(values)

    x = np.arange(len(log_values), dtype=float)
    slope, intercept = np.polyfit(x, log_values, 1)

    fitted = intercept + (slope * x)
    residuals = log_values - fitted
    sigma = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.01
    sigma = max(sigma, 0.01)

    future_x = np.arange(len(log_values), len(log_values) + horizon, dtype=float)
    future_log = intercept + (slope * future_x)

    z_score_80 = 1.28
    predicted = np.exp(future_log)
    lower = np.exp(future_log - z_score_80 * sigma)
    upper = np.exp(future_log + z_score_80 * sigma)

    history_window = close.tail(260)
    history = [
        {
            "date": idx.date().isoformat(),
            "close": round(float(price), 2),
        }
        for idx, price in history_window.items()
    ]

    last_date = close.index[-1]
    future_dates = pd.bdate_range(last_date + pd.Timedelta(days=1), periods=horizon)

    forecast = [
        {
            "date": dt.date().isoformat(),
            "predicted": round(float(pred), 2),
            "lower": round(float(low), 2),
            "upper": round(float(high), 2),
        }
        for dt, pred, low, high in zip(future_dates, predicted, lower, upper)
    ]

    stats = {
        "daily_trend_pct": round((float(np.exp(slope)) - 1.0) * 100.0, 3),
        "last_close": round(float(close.iloc[-1]), 2),
    }

    return history, forecast, stats


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/predict")
def predict(
    symbol: str = Query(..., min_length=1, max_length=10, description="Ticker symbool, bv AAPL"),
    horizon: int = Query(30, ge=7, le=45, description="Aantal handelsdagen om te voorspellen"),
) -> dict:
    ticker = symbol.strip().upper()
    if not ticker.isascii() or " " in ticker:
        raise HTTPException(status_code=400, detail="Ticker symbool is ongeldig.")

    close = _fetch_close_prices(ticker)
    history, forecast, stats = _build_forecast(close, horizon)

    return {
        "symbol": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon_days": horizon,
        "history": history,
        "forecast": forecast,
        "stats": stats,
        "disclaimer": "Dit is een statistische schatting en geen financieel advies.",
    }


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
