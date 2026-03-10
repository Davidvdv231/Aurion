from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

import pandas as pd
import yfinance as yf

from backend.config import Settings
from backend.errors import ServiceError
from backend.services.cache import CacheBackend
from backend.ticker_catalog import (
    AssetType,
    CRYPTO_EXACT_ALIASES,
    STOCK_EXACT_ALIASES,
    get_ticker_metadata,
    top_catalog_tickers,
)

logger = logging.getLogger("stock_predictor.market_data")

MARKET_SUFFIXES = (".AS", ".BR", ".PA", ".DE", ".L", ".MI", ".MC", ".SW", ".TO", ".V")
SUFFIX_CURRENCY_MAP = {
    ".AS": "EUR",
    ".BR": "EUR",
    ".PA": "EUR",
    ".DE": "EUR",
    ".MI": "EUR",
    ".MC": "EUR",
    ".L": "GBP",
    ".SW": "CHF",
    ".TO": "CAD",
    ".V": "CAD",
}


@dataclass(slots=True)
class MarketSeries:
    close: pd.Series
    resolved_symbol: str
    currency: str
    source: str


def normalize_symbol_input(symbol: str) -> str:
    return symbol.strip().upper()


def candidate_symbols(symbol: str, asset_type: AssetType) -> list[str]:
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
        if symbol.endswith("USD") and "-" not in symbol and len(symbol) > 3:
            candidates.append(f"{symbol[:-3]}-USD")
        if symbol.endswith("USDT") and "-" not in symbol and len(symbol) > 4:
            candidates.append(f"{symbol[:-4]}-USD")
        if "-" not in symbol:
            candidates.append(f"{symbol}-USD")

    return list(dict.fromkeys(candidates))


def infer_currency(symbol: str, asset_type: AssetType) -> str:
    normalized = symbol.upper()
    if asset_type == "crypto":
        return "USD"

    for suffix, currency in SUFFIX_CURRENCY_MAP.items():
        if normalized.endswith(suffix):
            return currency

    metadata = get_ticker_metadata(normalized, asset_type=asset_type)
    if metadata and metadata["region"] in {"NL", "BE", "FR", "DE", "IT", "ES"}:
        return "EUR"
    return "USD"


def _serialize_close_series(close: pd.Series) -> list[dict[str, Any]]:
    return [
        {"date": idx.date().isoformat(), "close": round(float(price), 6)}
        for idx, price in close.items()
    ]


def _deserialize_close_series(points: list[dict[str, Any]]) -> pd.Series:
    dates = [pd.Timestamp(row["date"]) for row in points]
    values = [float(row["close"]) for row in points]
    return pd.Series(values, index=dates, dtype=float)


def fetch_close_prices(
    symbol: str,
    asset_type: AssetType,
    cache_backend: CacheBackend,
    settings: Settings,
) -> MarketSeries:
    cache_key = f"history:{asset_type}:{symbol}"
    cached_payload = cache_backend.get_json(cache_key)
    if isinstance(cached_payload, dict):
        points = cached_payload.get("points")
        resolved_symbol = cached_payload.get("resolved_symbol")
        currency = cached_payload.get("currency")
        provider = cached_payload.get("provider", "yfinance")
        if (
            isinstance(points, list)
            and points
            and isinstance(resolved_symbol, str)
            and isinstance(currency, str)
        ):
            return MarketSeries(
                close=_deserialize_close_series(points),
                resolved_symbol=resolved_symbol,
                currency=currency,
                source=f"cache:{provider}",
            )

    end = datetime.now(timezone.utc)
    lookback_days = 730 if asset_type == "stock" else 540
    start = end - timedelta(days=lookback_days)
    insufficient_history_matches: list[str] = []
    provider_error: Exception | None = None

    for candidate in candidate_symbols(symbol, asset_type=asset_type):
        try:
            frame = yf.download(
                candidate,
                start=start.date(),
                end=(end + timedelta(days=1)).date(),
                interval="1d",
                auto_adjust=True,
                progress=False,
                timeout=12,
            )
        except Exception as exc:
            provider_error = exc
            logger.warning("yfinance download failed for candidate=%s: %s", candidate, exc)
            continue

        if not isinstance(frame, pd.DataFrame):
            logger.warning("yfinance returned invalid payload type for candidate=%s", candidate)
            continue

        if frame.empty or "Close" not in frame:
            continue

        close_column = frame["Close"]
        close = close_column.iloc[:, 0] if isinstance(close_column, pd.DataFrame) else close_column
        close = close.dropna()

        if len(close) < 60:
            insufficient_history_matches.append(candidate)
            continue

        currency = infer_currency(candidate, asset_type=asset_type)
        serialized = {
            "provider": "yfinance",
            "resolved_symbol": candidate,
            "currency": currency,
            "points": _serialize_close_series(close),
        }
        cache_backend.set_json(cache_key, serialized, settings.history_cache_ttl_seconds)

        return MarketSeries(
            close=close,
            resolved_symbol=candidate,
            currency=currency,
            source="yfinance",
        )

    if insufficient_history_matches:
        raise ServiceError(
            status_code=400,
            code="insufficient_history",
            message=(
                "Data gevonden, maar onvoldoende historiek voor een betrouwbare voorspelling "
                f"(ticker: {insufficient_history_matches[0]})."
            ),
            provider="yfinance",
        )

    if provider_error is not None:
        raise ServiceError(
            status_code=502,
            code="provider_unavailable",
            message="Marktdataprovider tijdelijk niet bereikbaar.",
            provider="yfinance",
            retryable=True,
        )

    detail = (
        "Geen cryptodata gevonden. Probeer bv BTC, ETH, SOL of BTC-USD."
        if asset_type == "crypto"
        else "Geen koersdata gevonden. Probeer een Yahoo ticker, bv AAPL, INGA.AS, HEIA.AS, KBC.BR."
    )
    raise ServiceError(status_code=404, code="not_found", message=detail, provider="yfinance")


def _fetch_yahoo_trending(region: str = "US", count: int = 20) -> list[str]:
    url = (
        f"https://query2.finance.yahoo.com/v1/finance/trending/{region}"
        f"?count={count}&lang=en-US&region={region}"
    )
    request = UrlRequest(url, headers={"User-Agent": "stock-crypto-predictor/0.5"})

    try:
        with urlopen(request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Yahoo trending fetch failed for region=%s: %s", region, exc)
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
    request = UrlRequest(url, headers={"User-Agent": "stock-crypto-predictor/0.5"})

    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("CoinGecko top assets fetch failed: %s", exc)
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


def resolve_top_assets(
    limit: int,
    asset_type: AssetType,
    cache_backend: CacheBackend,
    settings: Settings,
) -> tuple[list[dict], str]:
    cache_key = f"top-assets:{asset_type}"
    cached_payload = cache_backend.get_json(cache_key)
    if isinstance(cached_payload, dict):
        cached_items = cached_payload.get("items")
        cached_source = cached_payload.get("source", "unknown")
        if isinstance(cached_items, list) and len(cached_items) >= limit:
            return cached_items[:limit], f"cache:{cached_source}"

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

    cache_backend.set_json(
        cache_key,
        {"source": source, "items": items},
        settings.top_cache_ttl_seconds,
    )
    return items[:limit], source
