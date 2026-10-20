"""Lightweight exchange rate service using yfinance forex pairs."""

from __future__ import annotations

import logging
import math
import time
from threading import Lock

import pandas as pd

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


def _latest_rate(data: pd.DataFrame) -> float | None:
    if data.empty or "Close" not in data:
        return None
    close = data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    value = float(close.iloc[-1])
    return value if math.isfinite(value) and value > 0 else None


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


def try_get_exchange_rate(from_currency: str, to_currency: str) -> float | None:
    """
    Try to get the exchange rate from one currency to another.

    Returns the multiplier (1 unit of ``from_currency`` = rate units of ``to_currency``),
    or ``None`` when the rate cannot be determined. Same-currency conversions return 1.0.

    This is the preferred API because it forces callers to handle lookup failure
    explicitly instead of silently treating a failed lookup as "1.0".
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if from_currency == to_currency:
        return 1.0

    cached = _get_cached_rate(from_currency, to_currency)
    if cached is not None:
        return cached

    pair_key = (from_currency, to_currency)
    inverse_key = (to_currency, from_currency)

    symbol = _FOREX_PAIRS.get(pair_key)
    inverse_symbol = _FOREX_PAIRS.get(inverse_key)

    import yfinance as yf

    # Try direct pair
    if symbol:
        try:
            data = yf.download(symbol, period="1d", progress=False, auto_adjust=True, timeout=5)
            if not data.empty:
                rate = _latest_rate(data)
                if rate is not None:
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

    # Try inverse pair
    if inverse_symbol:
        try:
            data = yf.download(
                inverse_symbol, period="1d", progress=False, auto_adjust=True, timeout=5
            )
            if not data.empty:
                inverse_rate = _latest_rate(data)
                if inverse_rate is not None:
                    rate = 1.0 / inverse_rate
                    if not math.isfinite(rate) or rate <= 0:
                        return None
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

    # Try via USD pivot (from -> USD -> to).
    # Both legs must succeed independently. A silent fallback on either leg would
    # otherwise produce a structurally-wrong cross-rate (e.g. EUR->JPY = 1.0 * 149).
    if from_currency != "USD" and to_currency != "USD":
        rate_to_usd = try_get_exchange_rate(from_currency, "USD")
        rate_from_usd = try_get_exchange_rate("USD", to_currency)
        if rate_to_usd is not None and rate_from_usd is not None:
            rate = rate_to_usd * rate_from_usd
            if not math.isfinite(rate) or rate <= 0:
                return None
            _set_cached_rate(from_currency, to_currency, rate)
            return rate

    _logger.warning(
        "exchange_rate.fallback",
        extra={
            "from": from_currency,
            "to": to_currency,
            "detail": "Could not determine rate",
        },
    )
    return None


def get_exchange_rate(from_currency: str, to_currency: str) -> float:
    """
    Get exchange rate from one currency to another.

    Returns the multiplier: 1 unit of ``from_currency`` = rate units of ``to_currency``.
    Falls back to 1.0 if the rate cannot be determined.

    Prefer :func:`try_get_exchange_rate` when the caller can surface conversion
    failures to the user (e.g. via a data_warning). The 1.0 fallback is kept for
    backward compatibility only.
    """
    rate = try_get_exchange_rate(from_currency, to_currency)
    if rate is None:
        return 1.0
    return rate


def convert_price(price: float | None, rate: float) -> float | None:
    """Convert a single price value using the given rate. Returns None if input is None."""
    if price is None:
        return None
    return price * rate
