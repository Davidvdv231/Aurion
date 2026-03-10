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

try:
    from backend.ticker_catalog import (
        AssetType,
        CRYPTO_EXACT_ALIASES,
        STOCK_EXACT_ALIASES,
        get_ticker_metadata,
        search_tickers,
        top_catalog_tickers,
    )
except ModuleNotFoundError:
    # Support running as `python backend/main.py` as well as `python -m backend.main`.
    from ticker_catalog import (
        AssetType,
        CRYPTO_EXACT_ALIASES,
        STOCK_EXACT_ALIASES,
        get_ticker_metadata,
        search_tickers,
        top_catalog_tickers,
    )

app = FastAPI(title="Stock & Crypto Predictor API", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MARKET_SUFFIXES = (".AS", ".BR", ".PA", ".DE", ".L", ".MI", ".MC", ".SW", ".TO", ".V")
TOP_CACHE_TTL_SECONDS = 15 * 60
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"

_TOP_ASSETS_CACHE: dict[str, dict[str, Any]] = {
    "stock": {
        "expires_at": datetime.fromtimestamp(0, tz=timezone.utc),
        "items": [],
    },
    "crypto": {
        "expires_at": datetime.fromtimestamp(0, tz=timezone.utc),
        "items": [],
    },
}


def _normalize_symbol_input(symbol: str) -> str:
    return symbol.strip().upper()


def _candidate_symbols(symbol: str, asset_type: AssetType) -> list[str]:
    candidates: list[str] = []

    catalog_match = get_ticker_metadata(symbol, asset_type=asset_type)
    if catalog_match:
        candidates.append(catalog_match["symbol"])

    aliases = STOCK_EXACT_ALIASES if asset_type == "stock" else CRYPTO_EXACT_ALIASES
    alias = aliases.get(symbol)
    if alias:
        candidates.append(alias)

    candidates.append(symbol)

    if asset_type == "stock":
        if "." not in symbol:
            candidates.extend(f"{symbol}{suffix}" for suffix in MARKET_SUFFIXES)
            if symbol.endswith("A") and len(symbol) >= 5:
                candidates.append(f"{symbol[:-1]}.AS")
    else:
        # Common user inputs: BTC, BTCUSD, BTCUSDT, BTC-USD
        if symbol.endswith("USD") and "-" not in symbol and len(symbol) > 3:
            candidates.append(f"{symbol[:-3]}-USD")
        if symbol.endswith("USDT") and "-" not in symbol and len(symbol) > 4:
            candidates.append(f"{symbol[:-4]}-USD")
        if "-" not in symbol:
            candidates.append(f"{symbol}-USD")

    # Keep candidate order stable and remove duplicates.
    return list(dict.fromkeys(candidates))


def _fetch_close_prices(symbol: str, asset_type: AssetType) -> tuple[pd.Series, str]:
    end = datetime.now(timezone.utc)
    # Crypto is more volatile and often better with slightly shorter lookback.
    lookback_days = 730 if asset_type == "stock" else 540
    start = end - timedelta(days=lookback_days)
    insufficient_history_matches: list[str] = []

    for candidate in _candidate_symbols(symbol, asset_type=asset_type):
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

    if asset_type == "crypto":
        detail = "Geen cryptodata gevonden. Probeer bv BTC, ETH, SOL of BTC-USD."
    else:
        detail = "Geen koersdata gevonden. Probeer een Yahoo ticker, bv AAPL, INGA.AS, HEIA.AS, KBC.BR."

    raise HTTPException(status_code=404, detail=detail)


def _future_dates(last_date: pd.Timestamp, horizon: int, asset_type: AssetType) -> pd.DatetimeIndex:
    if asset_type == "crypto":
        return pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon, freq="D")
    return pd.bdate_range(last_date + pd.Timedelta(days=1), periods=horizon)


def _build_stat_forecast(close: pd.Series, horizon: int, asset_type: AssetType) -> tuple[list[dict], list[dict], dict]:
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

    history_window = close.tail(365 if asset_type == "crypto" else 260)
    history = [
        {
            "date": idx.date().isoformat(),
            "close": round(float(price), 2),
        }
        for idx, price in history_window.items()
    ]

    last_date = close.index[-1]
    future_dates = _future_dates(last_date, horizon, asset_type)

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
    request = Request(url, headers={"User-Agent": "stock-crypto-predictor/0.4"})

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


def _fetch_coingecko_top(count: int = 20) -> list[dict]:
    url = (
        "https://api.coingecko.com/api/v3/coins/markets"
        f"?vs_currency=usd&order=market_cap_desc&per_page={count}&page=1&sparkline=false"
    )
    request = Request(url, headers={"User-Agent": "stock-crypto-predictor/0.4"})

    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []

    if not isinstance(payload, list):
        return []

    items: list[dict] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            continue

        symbol_raw = row.get("symbol")
        name_raw = row.get("name")
        if not isinstance(symbol_raw, str) or not symbol_raw.strip():
            continue

        symbol = f"{symbol_raw.strip().upper()}-USD"
        name = name_raw.strip() if isinstance(name_raw, str) and name_raw.strip() else symbol_raw.upper()

        # Higher score for higher market cap rank.
        popularity = max(1000 - (index * 20), 100)
        items.append(
            {
                "symbol": symbol,
                "name": name,
                "exchange": "Crypto",
                "region": "GLOBAL",
                "popularity": popularity,
                "asset_type": "crypto",
            }
        )

    return items


def _resolve_top_assets(limit: int, asset_type: AssetType) -> tuple[list[dict], str]:
    cache_bucket = _TOP_ASSETS_CACHE[asset_type]
    now = datetime.now(timezone.utc)
    cached_items = cache_bucket.get("items", [])
    if cache_bucket.get("expires_at", now) > now and len(cached_items) >= limit:
        return cached_items[:limit], "cache"

    if asset_type == "stock":
        live_symbols: list[str] = []
        for region in ("US", "NL", "BE"):
            live_symbols.extend(_fetch_yahoo_trending(region=region, count=15))

        live_symbols = list(dict.fromkeys(live_symbols))
        source = "live_yahoo" if live_symbols else "catalog_fallback"

        fallback_symbols = [row["symbol"] for row in top_catalog_tickers(limit=25, asset_type="stock")]
        merged_symbols = list(dict.fromkeys([*live_symbols, *fallback_symbols]))

        items: list[dict] = []
        live_set = set(live_symbols)
        for symbol in merged_symbols:
            metadata = get_ticker_metadata(symbol, asset_type="stock")
            item = metadata or {
                "symbol": symbol,
                "name": symbol,
                "exchange": "Yahoo",
                "region": "GLOBAL",
                "popularity": 0,
                "asset_type": "stock",
            }
            item["source"] = "live_yahoo" if symbol in live_set else "catalog"
            items.append(item)
            if len(items) >= limit:
                break

    else:
        live_items = _fetch_coingecko_top(count=max(limit, 20))
        source = "live_coingecko" if live_items else "catalog_fallback"

        live_symbols = [row["symbol"] for row in live_items]
        fallback_symbols = [row["symbol"] for row in top_catalog_tickers(limit=25, asset_type="crypto")]
        merged_symbols = list(dict.fromkeys([*live_symbols, *fallback_symbols]))
        live_map = {row["symbol"]: row for row in live_items}

        items = []
        live_set = set(live_symbols)
        for symbol in merged_symbols:
            metadata = get_ticker_metadata(symbol, asset_type="crypto")
            item = metadata or live_map.get(symbol) or {
                "symbol": symbol,
                "name": symbol.replace("-USD", ""),
                "exchange": "Crypto",
                "region": "GLOBAL",
                "popularity": 0,
                "asset_type": "crypto",
            }
            item["source"] = "live_coingecko" if symbol in live_set else "catalog"
            items.append(item)
            if len(items) >= limit:
                break

    cache_bucket["expires_at"] = now + timedelta(seconds=TOP_CACHE_TTL_SECONDS)
    cache_bucket["items"] = items

    return items, source


def _extract_json_payload(text: str) -> dict:
    payload_text = text.strip()
    if payload_text.startswith("```"):
        payload_text = payload_text.strip("`")
        if payload_text.startswith("json"):
            payload_text = payload_text[4:]
        payload_text = payload_text.strip()

    try:
        parsed = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="AI model antwoord was geen geldige JSON.") from exc

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="AI model antwoord moet een JSON object zijn.")

    return parsed


def _normalize_ai_forecast_rows(
    forecast_rows: list,
    close: pd.Series,
    horizon: int,
    asset_type: AssetType,
) -> list[dict]:
    if len(forecast_rows) < horizon:
        raise HTTPException(
            status_code=502,
            detail="AI engine antwoord moet een 'forecast' lijst met voldoende punten bevatten.",
        )

    daily_vol = float(close.pct_change().dropna().tail(120).std())
    if np.isnan(daily_vol) or daily_vol <= 0:
        daily_vol = 0.015
    z_score_80 = 1.28

    future_dates = _future_dates(close.index[-1], horizon, asset_type)

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
        date_iso = (
            date_raw
            if isinstance(date_raw, str) and len(date_raw) >= 8
            else future_dates[index].date().isoformat()
        )

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

    return normalized_forecast


def _build_external_ai_forecast(
    symbol: str,
    close: pd.Series,
    horizon: int,
    asset_type: AssetType,
    api_url: str,
    api_key: str,
) -> tuple[list[dict], dict]:
    history_window = close.tail(220)
    payload = {
        "symbol": symbol,
        "asset_type": asset_type,
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
            detail=f"Externe AI gaf HTTP {exc.code}: {detail or 'geen detail'}",
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"Externe AI niet bereikbaar: {exc}") from exc

    parsed = _extract_json_payload(response_body)
    forecast_rows = parsed.get("forecast") if isinstance(parsed, dict) else None
    if not isinstance(forecast_rows, list):
        raise HTTPException(status_code=502, detail="Externe AI antwoord moet een forecast lijst bevatten.")

    normalized_forecast = _normalize_ai_forecast_rows(
        forecast_rows=forecast_rows,
        close=close,
        horizon=horizon,
        asset_type=asset_type,
    )

    model_info = {
        "provider": str(parsed.get("provider", "external")),
        "model": str(parsed.get("model", "custom-stock-llm")),
    }

    return normalized_forecast, model_info


def _build_openai_forecast(
    symbol: str,
    close: pd.Series,
    horizon: int,
    asset_type: AssetType,
    api_key: str,
) -> tuple[list[dict], dict]:
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip() or "gpt-5-mini"
    history_window = close.tail(200 if asset_type == "stock" else 240)
    history_payload = [
        {"date": idx.date().isoformat(), "close": round(float(price), 4)}
        for idx, price in history_window.items()
    ]

    calendar_hint = "trading days" if asset_type == "stock" else "calendar days"

    system_prompt = (
        "You are a quantitative market forecaster. Return strict JSON only. "
        "No markdown, no commentary."
    )
    user_prompt = (
        f"Create a {horizon}-step forecast for {symbol} ({asset_type}). "
        f"Use {calendar_hint} from the last history date. "
        "Return JSON object with key 'forecast' as an array of objects with: "
        "date (YYYY-MM-DD), predicted (number), lower (number), upper (number). "
        "History JSON follows:\n"
        f"{json.dumps(history_payload, separators=(',', ':'))}"
    )

    payload = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    request = Request(
        OPENAI_CHAT_COMPLETIONS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:220]
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI gaf HTTP {exc.code}: {detail or 'geen detail'}",
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI niet bereikbaar: {exc}") from exc

    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="OpenAI antwoord was geen geldige JSON.") from exc

    choices = parsed.get("choices") if isinstance(parsed, dict) else None
    if not isinstance(choices, list) or not choices:
        raise HTTPException(status_code=502, detail="OpenAI antwoord bevat geen choices.")

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None

    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        content = "".join(parts)

    if not isinstance(content, str) or not content.strip():
        raise HTTPException(status_code=502, detail="OpenAI gaf geen bruikbare content terug.")

    model_payload = _extract_json_payload(content)
    forecast_rows = model_payload.get("forecast")
    if not isinstance(forecast_rows, list):
        raise HTTPException(status_code=502, detail="OpenAI antwoord moet een forecast lijst bevatten.")

    normalized_forecast = _normalize_ai_forecast_rows(
        forecast_rows=forecast_rows,
        close=close,
        horizon=horizon,
        asset_type=asset_type,
    )

    model_info = {
        "provider": "openai",
        "model": str(parsed.get("model", model)),
    }

    return normalized_forecast, model_info


def _build_ai_forecast(symbol: str, close: pd.Series, horizon: int, asset_type: AssetType) -> tuple[list[dict], dict]:
    custom_api_url = os.getenv("STOCK_LLM_API_URL", "").strip()
    custom_api_key = os.getenv("STOCK_LLM_API_KEY", "").strip()

    if custom_api_url:
        return _build_external_ai_forecast(
            symbol=symbol,
            close=close,
            horizon=horizon,
            asset_type=asset_type,
            api_url=custom_api_url,
            api_key=custom_api_key,
        )

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_api_key:
        return _build_openai_forecast(
            symbol=symbol,
            close=close,
            horizon=horizon,
            asset_type=asset_type,
            api_key=openai_api_key,
        )

    raise HTTPException(
        status_code=400,
        detail="AI engine niet geconfigureerd. Stel OPENAI_API_KEY of STOCK_LLM_API_URL in.",
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/tickers")
def ticker_search(
    query: str = Query("", max_length=30, description="Zoektekst, bv K, KB, BTC"),
    limit: int = Query(20, ge=1, le=50),
    asset_type: AssetType = Query("stock", description="stock of crypto"),
) -> dict:
    return {
        "query": query,
        "asset_type": asset_type,
        "tickers": search_tickers(query=query, limit=limit, asset_type=asset_type),
    }


@app.get("/api/top-stocks")
def top_stocks(
    limit: int = Query(10, ge=5, le=25),
    asset_type: AssetType = Query("stock", description="stock of crypto"),
) -> dict:
    items, source = _resolve_top_assets(limit=limit, asset_type=asset_type)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asset_type": asset_type,
        "source": source,
        "items": items,
    }


@app.get("/api/predict")
def predict(
    symbol: str = Query(..., min_length=1, max_length=20, description="Ticker symbool, bv AAPL of BTC"),
    horizon: int = Query(30, ge=7, le=45, description="Aantal dagen om te voorspellen"),
    engine: Literal["stat", "ai"] = Query("stat", description="Voorspellingsengine"),
    asset_type: AssetType = Query("stock", description="stock of crypto"),
) -> dict:
    ticker = _normalize_symbol_input(symbol)
    if not ticker.isascii() or " " in ticker:
        raise HTTPException(status_code=400, detail="Ticker symbool is ongeldig.")

    close, resolved_ticker = _fetch_close_prices(ticker, asset_type=asset_type)
    history, stat_forecast, stats = _build_stat_forecast(close, horizon, asset_type=asset_type)

    engine_used = "stat"
    engine_note = "Statistische trend op historische koersdata."
    forecast = stat_forecast

    if engine == "ai":
        try:
            forecast, ai_model = _build_ai_forecast(resolved_ticker, close, horizon, asset_type=asset_type)
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
        "asset_type": asset_type,
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
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)



