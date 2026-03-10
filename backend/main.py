from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.ticker_catalog import EXACT_ALIASES, get_ticker_metadata, search_tickers, top_catalog_tickers

app = FastAPI(title="Stock Predictor API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MARKET_SUFFIXES = (".AS", ".BR", ".PA", ".DE", ".L", ".MI", ".MC", ".SW", ".TO", ".V")
TOP_CACHE_TTL_SECONDS = 15 * 60
_TOP_STOCKS_CACHE: dict[str, Any] = {
    "expires_at": datetime.fromtimestamp(0, tz=timezone.utc),
    "items": [],
}


def _candidate_symbols(symbol: str) -> list[str]:
    candidates: list[str] = []

    catalog_match = get_ticker_metadata(symbol)
    if catalog_match:
        candidates.append(catalog_match["symbol"])

    alias = EXACT_ALIASES.get(symbol)
    if alias:
        candidates.append(alias)

    candidates.append(symbol)

    if "." not in symbol:
        candidates.extend(f"{symbol}{suffix}" for suffix in MARKET_SUFFIXES)
        if symbol.endswith("A") and len(symbol) >= 5:
            candidates.append(f"{symbol[:-1]}.AS")

    # Keep candidate order stable and remove duplicates.
    return list(dict.fromkeys(candidates))


def _fetch_close_prices(symbol: str) -> tuple[pd.Series, str]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=730)
    insufficient_history_matches: list[str] = []

    for candidate in _candidate_symbols(symbol):
        frame = yf.download(
            candidate,
            start=start.date(),
            end=(end + timedelta(days=1)).date(),
            interval="1d",
            auto_adjust=True,
            progress=False,
        )

        if frame.empty or "Close" not in frame:
            continue

        close_column = frame["Close"]
        close = close_column.iloc[:, 0] if isinstance(close_column, pd.DataFrame) else close_column
        close = close.dropna()

        if len(close) < 60:
            insufficient_history_matches.append(candidate)
            continue

        return close, candidate

    if insufficient_history_matches:
        raise HTTPException(
            status_code=400,
            detail=(
                "Data gevonden, maar onvoldoende historiek voor een betrouwbare voorspelling "
                f"(ticker: {insufficient_history_matches[0]})."
            ),
        )

    raise HTTPException(
        status_code=404,
        detail="Geen koersdata gevonden. Probeer een Yahoo ticker, bv AAPL, INGA.AS, HEIA.AS, KBC.BR.",
    )


def _build_stat_forecast(close: pd.Series, horizon: int) -> tuple[list[dict], list[dict], dict]:
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


def _fetch_yahoo_trending(region: str = "US", count: int = 20) -> list[str]:
    url = (
        f"https://query2.finance.yahoo.com/v1/finance/trending/{region}"
        f"?count={count}&lang=en-US&region={region}"
    )
    request = Request(url, headers={"User-Agent": "stock-predictor/0.3"})

    try:
        with urlopen(request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []

    finance = payload.get("finance") if isinstance(payload, dict) else None
    result = finance.get("result") if isinstance(finance, dict) else None
    if not isinstance(result, list) or not result:
        return []

    quotes = result[0].get("quotes") if isinstance(result[0], dict) else None
    if not isinstance(quotes, list):
        return []

    symbols: list[str] = []
    for quote in quotes:
        symbol = quote.get("symbol") if isinstance(quote, dict) else None
        if isinstance(symbol, str) and symbol.strip():
            symbols.append(symbol.strip().upper())

    return symbols


def _resolve_top_stocks(limit: int) -> tuple[list[dict], str]:
    now = datetime.now(timezone.utc)
    cached_items = _TOP_STOCKS_CACHE.get("items", [])
    if _TOP_STOCKS_CACHE.get("expires_at", now) > now and len(cached_items) >= limit:
        return cached_items[:limit], "cache"

    live_symbols: list[str] = []
    for region in ("US", "NL", "BE"):
        live_symbols.extend(_fetch_yahoo_trending(region=region, count=15))

    live_symbols = list(dict.fromkeys(live_symbols))
    source = "live_yahoo" if live_symbols else "catalog_fallback"

    fallback_symbols = [row["symbol"] for row in top_catalog_tickers(limit=25)]
    merged_symbols = list(dict.fromkeys([*live_symbols, *fallback_symbols]))

    items: list[dict] = []
    live_set = set(live_symbols)
    for symbol in merged_symbols:
        metadata = get_ticker_metadata(symbol)
        item = metadata or {
            "symbol": symbol,
            "name": symbol,
            "exchange": "Yahoo",
            "region": "GLOBAL",
            "popularity": 0,
        }
        item["source"] = "live_yahoo" if symbol in live_set else "catalog"
        items.append(item)
        if len(items) >= limit:
            break

    _TOP_STOCKS_CACHE["expires_at"] = now + timedelta(seconds=TOP_CACHE_TTL_SECONDS)
    _TOP_STOCKS_CACHE["items"] = items

    return items, source


def _build_ai_forecast(symbol: str, close: pd.Series, horizon: int) -> tuple[list[dict], dict]:
    api_url = os.getenv("STOCK_LLM_API_URL", "").strip()
    api_key = os.getenv("STOCK_LLM_API_KEY", "").strip()

    if not api_url:
        raise HTTPException(
            status_code=400,
            detail=(
                "AI engine is niet geconfigureerd. Stel STOCK_LLM_API_URL in om een externe stock-AI te gebruiken."
            ),
        )

    history_window = close.tail(220)
    payload = {
        "symbol": symbol,
        "horizon_days": horizon,
        "history": [
            {"date": idx.date().isoformat(), "close": round(float(price), 4)}
            for idx, price in history_window.items()
        ],
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=25) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:200]
        raise HTTPException(
            status_code=502,
            detail=f"AI engine gaf HTTP {exc.code}: {detail or 'geen detail'}",
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"AI engine niet bereikbaar: {exc}") from exc

    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="AI engine gaf geen geldige JSON terug.") from exc

    forecast_rows = parsed.get("forecast") if isinstance(parsed, dict) else None
    if not isinstance(forecast_rows, list) or len(forecast_rows) < horizon:
        raise HTTPException(
            status_code=502,
            detail="AI engine antwoord moet een 'forecast' lijst met voldoende punten bevatten.",
        )

    daily_vol = float(close.pct_change().dropna().tail(120).std())
    if np.isnan(daily_vol) or daily_vol <= 0:
        daily_vol = 0.015
    z_score_80 = 1.28

    future_dates = pd.bdate_range(close.index[-1] + pd.Timedelta(days=1), periods=horizon)

    normalized_forecast: list[dict] = []
    for index in range(horizon):
        row = forecast_rows[index]
        if not isinstance(row, dict):
            raise HTTPException(status_code=502, detail="AI engine forecast-formaat is ongeldig.")

        predicted_raw = row.get("predicted", row.get("close"))
        try:
            predicted = float(predicted_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="AI engine voorspelling bevat geen geldig getal.") from exc

        date_raw = row.get("date")
        date_iso = date_raw if isinstance(date_raw, str) and len(date_raw) >= 8 else future_dates[index].date().isoformat()

        lower_raw = row.get("lower")
        upper_raw = row.get("upper")
        try:
            lower = float(lower_raw) if lower_raw is not None else predicted * (1 - z_score_80 * daily_vol)
            upper = float(upper_raw) if upper_raw is not None else predicted * (1 + z_score_80 * daily_vol)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="AI engine bandwaarden zijn ongeldig.") from exc

        lower = max(0.01, lower)
        upper = max(lower + 0.01, upper)

        normalized_forecast.append(
            {
                "date": date_iso,
                "predicted": round(predicted, 2),
                "lower": round(lower, 2),
                "upper": round(upper, 2),
            }
        )

    model_info = {
        "provider": str(parsed.get("provider", "external")),
        "model": str(parsed.get("model", "custom-stock-llm")),
    }

    return normalized_forecast, model_info


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/tickers")
def ticker_search(
    query: str = Query("", max_length=30, description="Zoektekst, bv K of KB"),
    limit: int = Query(20, ge=1, le=50),
) -> dict:
    return {
        "query": query,
        "tickers": search_tickers(query=query, limit=limit),
    }


@app.get("/api/top-stocks")
def top_stocks(limit: int = Query(10, ge=5, le=25)) -> dict:
    items, source = _resolve_top_stocks(limit)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "items": items,
    }


@app.get("/api/predict")
def predict(
    symbol: str = Query(..., min_length=1, max_length=15, description="Ticker symbool, bv AAPL"),
    horizon: int = Query(30, ge=7, le=45, description="Aantal handelsdagen om te voorspellen"),
    engine: Literal["stat", "ai"] = Query("stat", description="Voorspellingsengine"),
) -> dict:
    ticker = symbol.strip().upper()
    if not ticker.isascii() or " " in ticker:
        raise HTTPException(status_code=400, detail="Ticker symbool is ongeldig.")

    close, resolved_ticker = _fetch_close_prices(ticker)
    history, stat_forecast, stats = _build_stat_forecast(close, horizon)

    engine_used = "stat"
    engine_note = "Statistische trend op historische koersdata."
    forecast = stat_forecast

    if engine == "ai":
        try:
            forecast, ai_model = _build_ai_forecast(resolved_ticker, close, horizon)
            engine_used = "ai"
            engine_note = f"AI forecast via {ai_model['provider']} ({ai_model['model']})."
        except HTTPException as ai_error:
            engine_used = "stat_fallback"
            engine_note = (
                f"AI niet beschikbaar ({ai_error.detail}). Teruggevallen op statistische forecast."
            )

    return {
        "symbol": resolved_ticker,
        "requested_symbol": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon_days": horizon,
        "engine_requested": engine,
        "engine_used": engine_used,
        "engine_note": engine_note,
        "history": history,
        "forecast": forecast,
        "stats": stats,
        "disclaimer": "Dit is een statistische/AI schatting en geen financieel advies.",
    }


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
