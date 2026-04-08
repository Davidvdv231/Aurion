"""Lightweight exchange rate service using yfinance forex pairs."""

from __future__ import annotations

import logging
import time
from threading import Lock

_logger = logging.getLogger("stock_predictor.exchange_rates")

# Direct conversion pairs available via yfinance
_FOREX_PAIRS = {
    ("USD", "EUR"): "USDEUR=X",
    ("USD", "GBP"): "USDGBP=X",
    ("USD", "JPY"): "USDJPY=X",
    ("USD", "CHF"): "USDCHF=X",
    ("USD", "CAD"): "USDCAD=X",
    ("USD", "AUD"): "USDAUD=X",
    ("EUR", "USD"): "EURUSD=X",
    ("EUR", "GBP"): "EURGBP=X",
    ("GBP", "USD"): "GBPUSD=X",
}

_rate_cache: dict[str, tuple[float, float]] = {}  # key -> (rate, timestamp)
_rate_lock = Lock()
_CACHE_TTL_SECONDS = 3600  # 1 hour


def _get_cached_rate(from_cur: str, to_cur: str) -> float | None:
    """Return cached rate if fresh, else None."""
    key = f"{from_cur}_{to_cur}"
    with _rate_lock:
        if key in _rate_cache:
            rate, ts = _rate_cache[key]
            if time.monotonic() - ts < _CACHE_TTL_SECONDS:
                return rate
    return None


def _set_cached_rate(from_cur: str, to_cur: str, rate: float) -> None:
    key = f"{from_cur}_{to_cur}"
    with _rate_lock:
        _rate_cache[key] = (rate, time.monotonic())


def get_exchange_rate(from_currency: str, to_currency: str) -> float:
    """
    Get exchange rate from one currency to another.
    Returns the multiplier: 1 unit of from_currency = rate units of to_currency.

    Uses yfinance forex pairs with in-memory caching (1 hour TTL).
    Falls back to 1.0 if rate cannot be determined (with a warning log).
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if from_currency == to_currency:
        return 1.0

    # Check cache
    cached = _get_cached_rate(from_currency, to_currency)
    if cached is not None:
        return cached

    # Try direct pair
    pair_key = (from_currency, to_currency)
    inverse_key = (to_currency, from_currency)

    symbol = _FOREX_PAIRS.get(pair_key)
    inverse_symbol = _FOREX_PAIRS.get(inverse_key)

    import yfinance as yf

    # Try direct
    if symbol:
        try:
            data = yf.download(symbol, period="1d", progress=False, auto_adjust=True)
            if not data.empty:
                rate = float(data["Close"].iloc[-1])
                _set_cached_rate(from_currency, to_currency, rate)
                _logger.info(
                    "exchange_rate.fetched",
                    extra={
                        "from": from_currency,
                        "to": to_currency,
                        "rate": rate,
                        "source": symbol,
                    },
                )
                return rate
        except Exception as exc:
            _logger.warning(
                "exchange_rate.fetch_failed",
                extra={
                    "from": from_currency,
                    "to": to_currency,
                    "error": str(exc)[:100],
                },
            )

    # Try inverse
    if inverse_symbol:
        try:
            data = yf.download(inverse_symbol, period="1d", progress=False, auto_adjust=True)
            if not data.empty:
                inverse_rate = float(data["Close"].iloc[-1])
                if inverse_rate > 0:
                    rate = 1.0 / inverse_rate
                    _set_cached_rate(from_currency, to_currency, rate)
                    _logger.info(
                        "exchange_rate.fetched_inverse",
                        extra={
                            "from": from_currency,
                            "to": to_currency,
                            "rate": rate,
                            "source": inverse_symbol,
                        },
                    )
                    return rate
        except Exception as exc:
            _logger.warning(
                "exchange_rate.fetch_failed",
                extra={
                    "from": from_currency,
                    "to": to_currency,
                    "error": str(exc)[:100],
                },
            )

    # Try via USD pivot (from -> USD -> to)
    if from_currency != "USD" and to_currency != "USD":
        try:
            rate_to_usd = get_exchange_rate(from_currency, "USD")
            rate_from_usd = get_exchange_rate("USD", to_currency)
            if rate_to_usd != 1.0 or from_currency == "USD":
                rate = rate_to_usd * rate_from_usd
                _set_cached_rate(from_currency, to_currency, rate)
                return rate
        except Exception:
            pass

    # Fallback: return 1.0 and warn
    _logger.warning(
        "exchange_rate.fallback",
        extra={
            "from": from_currency,
            "to": to_currency,
            "detail": "Could not determine rate, using 1.0",
        },
    )
    return 1.0


def convert_price(price: float | None, rate: float) -> float | None:
    """Convert a single price value using the given rate. Returns None if input is None."""
    if price is None:
        return None
    return round(price * rate, 6)
