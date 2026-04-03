from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

import pandas as pd
import yfinance as yf

from backend.config import Settings
from backend.errors import ServiceError
from backend.services.cache import CacheBackend
from backend.ticker_catalog import (
    CRYPTO_EXACT_ALIASES,
    STOCK_EXACT_ALIASES,
    AssetType,
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

DataQuality = Literal["clean", "patched", "degraded"]


@dataclass(slots=True)
class MarketSeries:
    close: pd.Series
    resolved_symbol: str
    currency: str
    source: str
    data_quality: DataQuality = "clean"
    data_warnings: list[str] = field(default_factory=list)
    stale: bool = False


def _check_ohlcv_integrity(close: pd.Series, symbol: str) -> tuple[pd.Series, DataQuality, list[str]]:
    """Validate and patch OHLCV close series. Returns (patched_series, quality, warnings)."""
    warnings: list[str] = []
    quality: DataQuality = "clean"

    # NaN ratio check
    nan_count = int(close.isna().sum())
    nan_ratio = nan_count / len(close) if len(close) > 0 else 0.0
    if nan_ratio > 0.05:
        warnings.append(f"High NaN ratio ({nan_ratio:.1%}, {nan_count} points) — forward-filled.")
        quality = "degraded"
    elif nan_count > 0:
        warnings.append(f"{nan_count} NaN values forward-filled.")
        quality = "patched"

    if nan_count > 0:
        close = close.ffill().bfill()

    # Gap detection (>5 consecutive missing trading days)
    if hasattr(close.index, "to_series"):
        day_gaps = close.index.to_series().diff().dt.days
        max_gap = int(day_gaps.max()) if len(day_gaps) > 1 else 0
        if max_gap > 7:  # 5 trading days ≈ 7 calendar days
            warnings.append(f"Suspicious gap of {max_gap} calendar days detected.")
            if quality == "clean":
                quality = "patched"

    # Extreme outlier detection (daily return > ±50%)
    returns = close.pct_change().abs()
    extreme_count = int((returns > 0.50).sum())
    if extreme_count > 0:
        warnings.append(f"{extreme_count} extreme daily moves (>50%) — possible split or data error.")
        quality = "degraded"

    if warnings:
        logger.warning("OHLCV integrity issues for %s: %s", symbol, "; ".join(warnings))

    return close, quality, warnings


def _check_staleness(close: pd.Series, asset_type: AssetType) -> bool:
    """Return True if the most recent data point is older than 3 trading days."""
    if close.empty:
        return True
    last_date = pd.Timestamp(close.index[-1])
    now = pd.Timestamp.now(tz="UTC")
    if last_date.tzinfo is None:
        last_date = last_date.tz_localize("UTC")
    calendar_days = (now - last_date).days
    # 3 trading days ≈ 5 calendar days (weekends) for stocks, 3 days for crypto (24/7)
    threshold = 3 if asset_type == "crypto" else 5
    return calendar_days > threshold


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
        data_quality = cached_payload.get("data_quality", "clean")
        data_warnings = cached_payload.get("data_warnings", [])
        if (
            isinstance(points, list)
            and points
            and isinstance(resolved_symbol, str)
            and isinstance(currency, str)
        ):
            close = _deserialize_close_series(points)
            stale = _check_staleness(close, asset_type)
            warnings = list(data_warnings) if isinstance(data_warnings, list) else []
            if stale and "Data may be stale (last point >3 trading days old)." not in warnings:
                warnings.append("Data may be stale (last point >3 trading days old).")
            return MarketSeries(
                close=close,
                resolved_symbol=resolved_symbol,
                currency=currency,
                source=f"cache:{provider}",
                data_quality=data_quality if data_quality in {"clean", "patched", "degraded"} else "clean",
                data_warnings=warnings,
                stale=stale,
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

        close, data_quality, data_warnings = _check_ohlcv_integrity(close, candidate)
        stale = _check_staleness(close, asset_type)
        if stale:
            data_warnings.append("Data may be stale (last point >3 trading days old).")
            logger.warning("Stale data for %s: last date %s", candidate, close.index[-1])

        # Re-check length after patching (ffill shouldn't reduce it, but be safe)
        if len(close.dropna()) < 60:
            insufficient_history_matches.append(candidate)
            continue

        currency = infer_currency(candidate, asset_type=asset_type)
        serialized = {
            "provider": "yfinance",
            "resolved_symbol": candidate,
            "currency": currency,
            "data_quality": data_quality,
            "data_warnings": data_warnings,
            "points": _serialize_close_series(close),
        }
        cache_backend.set_json(cache_key, serialized, settings.history_cache_ttl_seconds)

        return MarketSeries(
            close=close,
            resolved_symbol=candidate,
            currency=currency,
            source="yfinance",
            data_quality=data_quality,
            data_warnings=data_warnings,
            stale=stale,
        )

    if insufficient_history_matches:
        raise ServiceError(
            status_code=400,
            code="insufficient_history",
            message=(
                "Data found but insufficient history for a reliable forecast "
                f"(ticker: {insufficient_history_matches[0]})."
            ),
            provider="yfinance",
        )

    if provider_error is not None:
        raise ServiceError(
            status_code=502,
            code="provider_unavailable",
            message="Market data provider temporarily unavailable.",
            provider="yfinance",
            retryable=True,
        )

    detail = (
        "No crypto data found. Try BTC, ETH, SOL or BTC-USD."
        if asset_type == "crypto"
        else "No price data found. Try a Yahoo ticker like AAPL, INGA.AS, HEIA.AS, KBC.BR."
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
