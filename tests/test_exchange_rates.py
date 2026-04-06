"""Tests for the exchange rate service."""

from __future__ import annotations

import time
from unittest.mock import patch

import pandas as pd
import pytest

from backend.services.exchange_rates import (
    _rate_cache,
    _set_cached_rate,
    convert_price,
    get_exchange_rate,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure exchange rate cache is empty for each test."""
    _rate_cache.clear()
    yield
    _rate_cache.clear()


def _mock_download(close_value: float):
    """Return a mock yfinance download result with the given close price."""
    idx = pd.DatetimeIndex([pd.Timestamp("2026-04-07")])
    return pd.DataFrame({"Close": [close_value]}, index=idx)


# ── Identity conversion ──────────────────────────────────────────────


def test_same_currency_returns_one():
    assert get_exchange_rate("USD", "USD") == 1.0
    assert get_exchange_rate("EUR", "EUR") == 1.0


# ── Direct pair lookup ────────────────────────────────────────────────


@patch("yfinance.download")
def test_direct_pair(mock_dl):
    mock_dl.return_value = _mock_download(0.92)
    rate = get_exchange_rate("USD", "EUR")
    assert rate == pytest.approx(0.92)
    mock_dl.assert_called_once()
    # Verify the result is cached — second call should not trigger download
    assert get_exchange_rate("USD", "EUR") == pytest.approx(0.92)
    mock_dl.assert_called_once()


# ── Cache TTL ─────────────────────────────────────────────────────────


def test_cache_returns_fresh_value():
    _set_cached_rate("USD", "JPY", 149.5)
    assert get_exchange_rate("USD", "JPY") == pytest.approx(149.5)


def test_cache_expires():
    _rate_cache["USD_CHF"] = (0.88, time.monotonic() - 7200)  # 2 hours ago
    with patch("yfinance.download") as mock_dl:
        mock_dl.return_value = _mock_download(0.89)
        rate = get_exchange_rate("USD", "CHF")
        assert rate == pytest.approx(0.89)
        mock_dl.assert_called_once()


# ── Fallback to 1.0 ──────────────────────────────────────────────────


@patch("yfinance.download")
def test_fallback_returns_one_on_failure(mock_dl):
    mock_dl.side_effect = Exception("network error")
    rate = get_exchange_rate("USD", "EUR")
    assert rate == 1.0


@patch("yfinance.download")
def test_fallback_on_empty_data(mock_dl):
    mock_dl.return_value = pd.DataFrame()
    rate = get_exchange_rate("USD", "EUR")
    assert rate == 1.0


# ── USD pivot (cross-rate) ────────────────────────────────────────────


@patch("yfinance.download")
def test_cross_rate_via_usd_pivot(mock_dl):
    # EUR->JPY should go via EUR->USD->JPY
    def download_side_effect(symbol, **kwargs):
        if "EURUSD" in symbol:
            return _mock_download(1.08)
        if "USDJPY" in symbol:
            return _mock_download(149.0)
        return pd.DataFrame()

    mock_dl.side_effect = download_side_effect
    rate = get_exchange_rate("EUR", "JPY")
    assert rate == pytest.approx(1.08 * 149.0, rel=0.01)


# ── convert_price ─────────────────────────────────────────────────────


def test_convert_price_basic():
    assert convert_price(100.0, 0.92) == pytest.approx(92.0)


def test_convert_price_none_input():
    assert convert_price(None, 0.92) is None


def test_convert_price_identity():
    assert convert_price(42.123456, 1.0) == pytest.approx(42.123456)
